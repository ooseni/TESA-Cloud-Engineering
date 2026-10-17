# A small instance with no inbound rules and no public address. Session Manager port forwarding through it
# is the only path to the database: no bastion host, no SSH key, no open port.

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_iam_policy_document" "client_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "client" {
  name               = "tesa-m11-access"
  assume_role_policy = data.aws_iam_policy_document.client_assume.json
}

resource "aws_iam_role_policy_attachment" "client_ssm" {
  role       = aws_iam_role.client.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "client" {
  name = "tesa-m11-access"
  role = aws_iam_role.client.name
}

resource "aws_instance" "client" {
  #checkov:skip=CKV_AWS_126:Detailed monitoring is not needed for a lab access instance.
  ami                         = data.aws_ssm_parameter.al2023.value
  instance_type               = "t3.micro"
  subnet_id                   = aws_subnet.private[0].id
  vpc_security_group_ids      = [aws_security_group.client.id]
  iam_instance_profile        = aws_iam_instance_profile.client.name
  associate_public_ip_address = false
  ebs_optimized               = true

  metadata_options {
    http_tokens   = "required" # IMDSv2 only
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 8
    encrypted   = true
  }

  tags = { Name = "tesa-m11-access" }

  lifecycle {
    ignore_changes = [ami] # a newer AMI should not replace a running instance
  }

  depends_on = [aws_vpc_endpoint.ssm]
}
