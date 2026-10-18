# The original pipeline's stack, hardened: a VPC with one public subnet and a web server. The server is
# immutable: no SSH key, no port 22 and no instance role. To change it, change this code and let the
# pipeline replace it. Keeping IAM out of the stack keeps it out of the apply role's permissions too.

resource "aws_vpc" "main" {
  #checkov:skip=CKV2_AWS_11:Flow logs are listed under production changes for this one-instance stack.
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "tesa-m13-vpc" }
}

resource "aws_default_security_group" "default" {
  vpc_id = aws_vpc.main.id # no rules: nothing can use the default group
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "tesa-m13-igw" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 1)
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = false
  tags                    = { Name = "tesa-m13-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "tesa-m13-public" }
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

resource "aws_security_group" "web" {
  name        = "tesa-m13-web"
  description = "HTTP in from anywhere; HTTPS out; no SSH"
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  #checkov:skip=CKV_AWS_260:A public web server must accept HTTP from anywhere; an HTTPS load balancer is listed under production changes.
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
  description       = "HTTPS to the package repositories"
}

# AWS's public parameter names the current Amazon Linux 2023 image; the original hard-coded an AMI ID
# that exists in one Region only.
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_instance" "web" {
  #checkov:skip=CKV_AWS_88:The stack is a web server with its own public address; a load balancer is listed under production changes.
  #checkov:skip=CKV_AWS_126:Detailed monitoring is not needed for this stack.
  #checkov:skip=CKV2_AWS_41:Deliberately no instance role: the server is immutable, and the apply role has no IAM permissions.
  ami                         = data.aws_ssm_parameter.al2023.value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.web.id]
  associate_public_ip_address = true
  ebs_optimized               = true

  user_data                   = file("${path.module}/user_data.sh")
  user_data_replace_on_change = true

  metadata_options {
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 8
    encrypted   = true
  }

  tags = { Name = "tesa-m13-web" }

  lifecycle {
    ignore_changes = [ami]
  }
}
