# The lab's network, kept: one VPC, an internet gateway and one public subnet. Hardened: the subnet no
# longer hands out public addresses by default, and the default security group allows nothing.

resource "aws_vpc" "main" {
  #checkov:skip=CKV2_AWS_11:Flow logs are listed under production changes for this one-instance lab.
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "tesa-m12-vpc" }
}

resource "aws_default_security_group" "default" {
  vpc_id = aws_vpc.main.id # no rules: nothing can use the default group
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "tesa-m12-igw" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = false # the instance asks for its own public address, explicitly

  tags = { Name = "tesa-m12-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "tesa-m12-public" }
}

resource "aws_route" "internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Port 80 in for visitors; out, only HTTPS (package repositories and Systems Manager). No port 22.
resource "aws_security_group" "web" {
  name        = "tesa-m12-web"
  description = "HTTP in from anywhere; HTTPS out; no SSH"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  #checkov:skip=CKV_AWS_260:A public web server must accept HTTP from anywhere; an HTTPS load balancer in front is listed under production changes.
  security_group_id = aws_security_group.web.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  description       = "HTTP from visitors"
}

resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.web.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "HTTPS to package repositories and Systems Manager"
}
