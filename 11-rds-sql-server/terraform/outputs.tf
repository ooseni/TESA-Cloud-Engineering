output "region" {
  description = "AWS Region."
  value       = var.region
}

output "db_address" {
  description = "The database's private DNS name."
  value       = aws_db_instance.db.address
}

output "db_port" {
  description = "SQL Server port."
  value       = aws_db_instance.db.port
}

output "master_secret_arn" {
  description = "The RDS-managed secret holding the master user's name and password."
  value       = aws_db_instance.db.master_user_secret[0].secret_arn
}

output "app_secret_arn" {
  description = "The secret holding the squad_app login's password."
  value       = aws_secretsmanager_secret.app.arn
}

output "access_instance_id" {
  description = "The instance used for Session Manager port forwarding."
  value       = aws_instance.client.id
}

output "db_security_group_id" {
  description = "The database's security group."
  value       = aws_security_group.db.id
}
