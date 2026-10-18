# The test host: an Ubuntu instance that runs the rest of the demo in Docker (the gateway, the vendor mock,
# the re-query worker, the sync consumer and PostgreSQL as the system of record) against the real table and
# brokers, and runs the tests. No key pair and no inbound rule: it is driven through Systems Manager.

resource "aws_s3_bucket" "bundle" {
  #checkov:skip=CKV_AWS_18:Holds one zip for a one-hour run.
  #checkov:skip=CKV_AWS_21:Versioning is not needed for a bundle that is rebuilt each run.
  #checkov:skip=CKV_AWS_144:Same reason, for replication.
  #checkov:skip=CKV_AWS_145:SSE-S3 encrypts the bundle; it holds no secret.
  #checkov:skip=CKV2_AWS_61:Destroyed after the run, so no lifecycle rule.
  #checkov:skip=CKV2_AWS_62:No consumer needs event notifications.
  bucket_prefix = "paygate-run-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "bundle" {
  bucket                  = aws_s3_bucket.bundle.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "bundle" {
  bucket = aws_s3_bucket.bundle.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "demo" {
  bucket = aws_s3_bucket.bundle.id
  key    = "demo.zip"
  source = "${var.bundle_dir}/demo.zip"
  etag   = filemd5("${var.bundle_dir}/demo.zip")
}

data "aws_iam_policy_document" "ec2_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "host" {
  statement {
    sid       = "Bundle"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.bundle.arn}/*"]
  }

  statement {
    sid = "PaymentsTable"
    actions = ["dynamodb:DescribeTable", "dynamodb:DescribeTimeToLive", "dynamodb:PutItem", "dynamodb:GetItem",
    "dynamodb:UpdateItem", "dynamodb:Query"]
    resources = [aws_dynamodb_table.payments.arn, "${aws_dynamodb_table.payments.arn}/index/attention"]
  }

  statement {
    sid       = "KafkaCluster"
    actions   = ["kafka-cluster:Connect", "kafka-cluster:DescribeCluster", "kafka-cluster:WriteDataIdempotently"]
    resources = [aws_msk_cluster.paygate.arn]
  }

  statement {
    sid = "KafkaTopics"
    actions = ["kafka-cluster:CreateTopic", "kafka-cluster:DescribeTopic", "kafka-cluster:ReadData",
    "kafka-cluster:WriteData"]
    resources = [local.kafka_topics]
  }

  statement {
    sid       = "KafkaGroups"
    actions   = ["kafka-cluster:AlterGroup", "kafka-cluster:DescribeGroup"]
    resources = [local.kafka_groups]
  }
}

resource "aws_iam_role" "host" {
  name               = "paygate-run-host"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

resource "aws_iam_role_policy" "host" {
  name   = "host"
  role   = aws_iam_role.host.id
  policy = data.aws_iam_policy_document.host.json
}

resource "aws_iam_role_policy_attachment" "host_ssm" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "host" {
  name = "paygate-run-host"
  role = aws_iam_role.host.name
}

data "aws_ssm_parameter" "ubuntu" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

resource "aws_instance" "host" {
  #checkov:skip=CKV_AWS_88:The host needs a public address to reach package mirrors; it accepts no connections.
  #checkov:skip=CKV_AWS_126:Detailed monitoring is not needed for a test run.
  #checkov:skip=CKV_AWS_135:t3 instances are EBS-optimised by default.
  ami                         = data.aws_ssm_parameter.ubuntu.value
  instance_type               = var.host_instance_type
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.host.id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.host.name

  user_data                   = file("${path.module}/host_setup.sh")
  user_data_replace_on_change = true

  metadata_options {
    http_tokens = "required"
    # 2, not 1: the containers reach the metadata service through Docker's bridge, one hop further
    http_put_response_hop_limit = 2
    http_endpoint               = "enabled"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
    encrypted   = true
  }

  tags = { Name = "paygate-run-host" }

  lifecycle {
    ignore_changes = [ami]
  }
}
