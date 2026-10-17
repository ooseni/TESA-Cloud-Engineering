# An isolated VPC: two private subnets for the DB subnet group, no internet gateway and no NAT gateway.
# The only ways in are AWS Systems Manager, through interface endpoints, and the local route.

resource "aws_vpc" "main" {
  #checkov:skip=CKV2_AWS_11:The VPC has no route to or from the internet; flow logs are listed under production changes.
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true # needed for the interface endpoints' private DNS names

  tags = { Name = "tesa-m11-vpc" }
}

# The default security group allows traffic between its members; with no rules, nothing can use it.
resource "aws_default_security_group" "default" {
  vpc_id = aws_vpc.main.id
}

resource "aws_subnet" "private" {
  count = 2

  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 1)
  availability_zone = var.availability_zones[count.index]

  tags = { Name = "tesa-m11-private-${var.availability_zones[count.index]}" }
}

# Only the local route: nothing in these subnets can reach, or be reached from, the internet.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "tesa-m11-private" }
}

resource "aws_route_table_association" "private" {
  count = 2

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ---------------------------------------------------------------------------- security groups

resource "aws_security_group" "db" {
  name        = "tesa-m11-db"
  description = "SQL Server: 1433 from the access instance only"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "client" {
  name        = "tesa-m11-client"
  description = "Access instance: no inbound rules; out to the database and the SSM endpoints"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "endpoints" {
  name        = "tesa-m11-endpoints"
  description = "SSM interface endpoints: HTTPS from the access instance"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "db_from_client" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.client.id
  ip_protocol                  = "tcp"
  from_port                    = 1433
  to_port                      = 1433
  description                  = "SQL Server from the access instance"
}

resource "aws_vpc_security_group_egress_rule" "client_to_db" {
  security_group_id            = aws_security_group.client.id
  referenced_security_group_id = aws_security_group.db.id
  ip_protocol                  = "tcp"
  from_port                    = 1433
  to_port                      = 1433
  description                  = "SQL Server, for port forwarding"
}

resource "aws_vpc_security_group_egress_rule" "client_to_endpoints" {
  security_group_id            = aws_security_group.client.id
  referenced_security_group_id = aws_security_group.endpoints.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "SSM endpoints"
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_from_client" {
  security_group_id            = aws_security_group.endpoints.id
  referenced_security_group_id = aws_security_group.client.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "HTTPS from the access instance"
}

# ---------------------------------------------------------------------------- SSM endpoints

# Session Manager needs these three; one zone is enough for a lab access path.
resource "aws_vpc_endpoint" "ssm" {
  for_each = toset(["ssm", "ssmmessages", "ec2messages"])

  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.private[0].id]
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = { Name = "tesa-m11-${each.value}" }
}
