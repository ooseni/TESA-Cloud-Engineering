# Two zones. The brokers and the relay's network interfaces sit in private subnets with no route out; the
# test host sits in a public subnet so it can install Docker and pull images, and accepts no connections.

resource "aws_vpc" "main" {
  #checkov:skip=CKV2_AWS_11:Flow logs are part of the design (network page), not of a one-hour test run.
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "paygate-run" }
}

resource "aws_default_security_group" "default" {
  vpc_id = aws_vpc.main.id # no rules: nothing can use the default group
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "paygate-run" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false
  tags                    = { Name = "paygate-run-public-${count.index}" }
}

resource "aws_subnet" "data" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 32 + count.index)
  availability_zone = var.availability_zones[count.index]
  tags              = { Name = "paygate-run-data-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "paygate-run-public" }
}

resource "aws_route" "internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "data" {
  vpc_id = aws_vpc.main.id # local route only
  tags   = { Name = "paygate-run-data" }
}

resource "aws_route_table_association" "data" {
  count          = 2
  subnet_id      = aws_subnet.data[count.index].id
  route_table_id = aws_route_table.data.id
}

# ---------------------------------------------------------------------------- security groups

resource "aws_security_group" "msk" {
  name        = "paygate-run-msk"
  description = "Kafka with IAM authentication over TLS, from the relay and the test host only"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "relay" {
  name        = "paygate-run-relay"
  description = "The relay function: out to the brokers only"
  vpc_id      = aws_vpc.main.id
}

resource "aws_security_group" "host" {
  name        = "paygate-run-host"
  description = "The test host: no inbound; out to package mirrors, AWS APIs and the brokers"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "msk_from" {
  for_each                     = { relay = aws_security_group.relay.id, host = aws_security_group.host.id }
  security_group_id            = aws_security_group.msk.id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = 9098
  to_port                      = 9098
  description                  = "Kafka, IAM over TLS, from the ${each.key}"
}

resource "aws_vpc_security_group_egress_rule" "to_msk" {
  for_each                     = { relay = aws_security_group.relay.id, host = aws_security_group.host.id }
  security_group_id            = each.value
  referenced_security_group_id = aws_security_group.msk.id
  ip_protocol                  = "tcp"
  from_port                    = 9098
  to_port                      = 9098
  description                  = "Kafka, IAM over TLS"
}

resource "aws_vpc_security_group_egress_rule" "host_web" {
  #checkov:skip=CKV_AWS_382:The host installs packages and pulls images from the internet; it accepts no connections.
  for_each          = { https = 443, http = 80 }
  security_group_id = aws_security_group.host.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = each.value
  to_port           = each.value
  description       = "${upper(each.key)}: Ubuntu mirrors, PyPI, Docker Hub, AWS APIs"
}
