output "site_url" {
  description = "The web server's address."
  value       = "http://${aws_instance.web.public_ip}"
}

output "instance_id" {
  description = "The web server's instance ID."
  value       = aws_instance.web.id
}
