output "region" {
  description = "AWS Region."
  value       = var.region
}

output "instance_id" {
  description = "The web server's instance ID."
  value       = aws_instance.web.id
}

output "site_url" {
  description = "The web server's address."
  value       = "http://${aws_instance.web.public_ip}"
}

output "security_group_id" {
  description = "The web server's security group."
  value       = aws_security_group.web.id
}

output "session_command" {
  description = "Open a shell on the instance without SSH."
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.web.id}"
}
