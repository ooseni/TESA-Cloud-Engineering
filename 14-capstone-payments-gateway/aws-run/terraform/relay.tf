# The relay (ADR-0002) as the design runs it: an AWS Lambda function on the table's stream, publishing each
# change to Amazon MSK. The code is the demo's paygate.relay.handler, unchanged.

resource "aws_sqs_queue" "relay_failures" {
  name                    = "paygate-run-relay-failures"
  sqs_managed_sse_enabled = true
}

resource "aws_cloudwatch_log_group" "relay" {
  #checkov:skip=CKV_AWS_158:Function logs for a one-hour run; a customer managed key is listed for production.
  #checkov:skip=CKV_AWS_338:Seven days is enough for a run that is destroyed the same day.
  name              = "/aws/lambda/paygate-run-relay"
  retention_in_days = 7
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "relay" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.relay.arn}:*"]
  }

  statement {
    #checkov:skip=CKV_AWS_356:Lambda manages the network interfaces of functions in a VPC; these actions take no resource.
    #checkov:skip=CKV_AWS_111:Same reason.
    sid = "NetworkInterfaces"
    actions = ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface",
    "ec2:AssignPrivateIpAddresses", "ec2:UnassignPrivateIpAddresses"]
    resources = ["*"]
  }

  statement {
    sid       = "ReadTheStream"
    actions   = ["dynamodb:DescribeStream", "dynamodb:GetRecords", "dynamodb:GetShardIterator", "dynamodb:ListStreams"]
    resources = [aws_dynamodb_table.payments.stream_arn]
  }

  statement {
    sid       = "FailedBatches"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.relay_failures.arn]
  }

  statement {
    sid       = "KafkaConnect"
    actions   = ["kafka-cluster:Connect", "kafka-cluster:WriteDataIdempotently"]
    resources = [aws_msk_cluster.paygate.arn]
  }

  statement {
    sid       = "KafkaPublish"
    actions   = ["kafka-cluster:DescribeTopic", "kafka-cluster:WriteData"]
    resources = [local.kafka_topics]
  }
}

resource "aws_iam_role" "relay" {
  name               = "paygate-run-relay"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy" "relay" {
  name   = "relay"
  role   = aws_iam_role.relay.id
  policy = data.aws_iam_policy_document.relay.json
}

resource "aws_lambda_function" "relay" {
  #checkov:skip=CKV_AWS_50:X-Ray tracing is listed for production.
  #checkov:skip=CKV_AWS_115:Concurrency follows the stream's shards; no reserved limit is needed for a test run.
  #checkov:skip=CKV_AWS_116:Stream invocations are synchronous; failed batches go to the event source mapping's SQS destination.
  #checkov:skip=CKV_AWS_173:The environment holds only the broker addresses and the topic name, nothing secret.
  #checkov:skip=CKV_AWS_272:Code signing is listed for production.
  function_name    = "paygate-run-relay"
  role             = aws_iam_role.relay.arn
  runtime          = "python3.12"
  handler          = "paygate.relay.handler"
  filename         = "${var.bundle_dir}/relay.zip"
  source_code_hash = filebase64sha256("${var.bundle_dir}/relay.zip")
  memory_size      = 256
  timeout          = 60

  vpc_config {
    subnet_ids         = aws_subnet.data[*].id
    security_group_ids = [aws_security_group.relay.id]
  }

  environment {
    variables = {
      KAFKA_BOOTSTRAP = aws_msk_cluster.paygate.bootstrap_brokers_sasl_iam
      KAFKA_AUTH      = "iam"
      KAFKA_TOPIC     = "transaction-state"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.relay.name
  }

  depends_on = [aws_iam_role_policy.relay]
}

resource "aws_lambda_event_source_mapping" "relay" {
  event_source_arn                   = aws_dynamodb_table.payments.stream_arn
  function_name                      = aws_lambda_function.relay.arn
  starting_position                  = "TRIM_HORIZON"
  batch_size                         = 100
  maximum_batching_window_in_seconds = 1
  bisect_batch_on_function_error     = true
  maximum_retry_attempts             = -1 # retry until the records leave the stream: nothing is dropped early

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.relay_failures.arn
    }
  }
}
