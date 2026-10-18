# The lab's instance, hardened: no SSH key or port, Session Manager for administration, IMDSv2 only,
# an encrypted gp3 disk, and nginx installed by user data so port 80 actually serves something.

# AWS publishes the current Amazon Linux 2023 AMI here, so no name filter can match the wrong image.
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "web" {
  name               = "tesa-m12-web"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.web.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "web" {
  name = "tesa-m12-web"
  role = aws_iam_role.web.name
}

resource "aws_instance" "web" {
  #checkov:skip=CKV_AWS_88:The lab's design is a web server with its own public address; a load balancer in front is listed under production changes.
  #checkov:skip=CKV_AWS_126:Detailed monitoring is not needed for a one-instance lab.
  ami                         = data.aws_ssm_parameter.al2023.value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.web.id]
  iam_instance_profile        = aws_iam_instance_profile.web.name
  associate_public_ip_address = true
  ebs_optimized               = true

  user_data                   = file("${path.module}/user_data.sh")
  user_data_replace_on_change = true

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only: a stolen request URL cannot read the role's credentials
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 8
    encrypted   = true
  }

  tags = { Name = "tesa-m12-web" }

  lifecycle {
    ignore_changes = [ami] # a newer AMI should not replace the running instance
  }
}
