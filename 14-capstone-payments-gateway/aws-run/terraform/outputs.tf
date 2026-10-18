output "region" {
  description = "The run's Region."
  value       = var.region
}

output "table_name" {
  description = "The payments table."
  value       = aws_dynamodb_table.payments.name
}

output "bootstrap_brokers" {
  description = "Amazon MSK's brokers for IAM authentication over TLS (port 9098)."
  value       = aws_msk_cluster.paygate.bootstrap_brokers_sasl_iam
}

output "host_instance_id" {
  description = "The test host, for Systems Manager."
  value       = aws_instance.host.id
}

output "bundle_bucket" {
  description = "Where the demo's code is uploaded for the host."
  value       = aws_s3_bucket.bundle.id
}

output "relay_function" {
  description = "The relay function."
  value       = aws_lambda_function.relay.function_name
}

output "relay_failures_queue" {
  description = "Batches the relay could not publish, if any."
  value       = aws_sqs_queue.relay_failures.url
}
