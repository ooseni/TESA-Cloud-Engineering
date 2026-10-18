# These become the repository's Actions variables (see the module README). None of them is a secret.

output "state_bucket" {
  description = "TF_STATE_BUCKET: the state bucket's name."
  value       = aws_s3_bucket.state.id
}

output "plan_role_arn" {
  description = "TF_PLAN_ROLE_ARN: assumed by pull request runs."
  value       = aws_iam_role.ci["plan"].arn
}

output "apply_role_arn" {
  description = "TF_APPLY_ROLE_ARN: assumed by runs on main."
  value       = aws_iam_role.ci["apply"].arn
}

output "region" {
  description = "AWS_REGION."
  value       = var.region
}
