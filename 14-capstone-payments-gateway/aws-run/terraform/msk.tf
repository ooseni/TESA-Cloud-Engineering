# Amazon MSK in place of the demo's single broker: two brokers in two zones, IAM authentication only, TLS
# everywhere. The design's three brokers become two here, so topics keep two replicas, not three.

resource "aws_msk_configuration" "paygate" {
  name           = "paygate-run"
  kafka_versions = [var.kafka_version]

  server_properties = <<-PROPERTIES
    auto.create.topics.enable=false
    default.replication.factor=2
    min.insync.replicas=1
    num.partitions=12
  PROPERTIES
}

resource "aws_cloudwatch_log_group" "msk" {
  #checkov:skip=CKV_AWS_158:Broker logs for a one-hour run; a customer managed key is listed for production.
  #checkov:skip=CKV_AWS_338:Seven days is enough for a run that is destroyed the same day.
  name              = "/paygate-run/msk"
  retention_in_days = 7
}

resource "aws_msk_cluster" "paygate" {
  #checkov:skip=CKV_AWS_81:Encrypted at rest with the AWS managed key; a customer managed key is listed for production.
  cluster_name           = "paygate-run"
  kafka_version          = var.kafka_version
  number_of_broker_nodes = 2

  broker_node_group_info {
    instance_type   = var.broker_instance_type
    client_subnets  = aws_subnet.data[*].id
    security_groups = [aws_security_group.msk.id]
    storage_info {
      ebs_storage_info {
        volume_size = 10
      }
    }
  }

  client_authentication {
    unauthenticated = false
    sasl {
      iam = true
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  configuration_info {
    arn      = aws_msk_configuration.paygate.arn
    revision = aws_msk_configuration.paygate.latest_revision
  }

  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk.name
      }
    }
  }
}

locals {
  # IAM resources for Kafka: cluster/NAME/UUID becomes topic/NAME/UUID/* and group/NAME/UUID/*
  kafka_topics = "${replace(aws_msk_cluster.paygate.arn, ":cluster/", ":topic/")}/*"
  kafka_groups = "${replace(aws_msk_cluster.paygate.arn, ":cluster/", ":group/")}/*"
}
