# The application login's password. It is generated as an ephemeral value and sent to Secrets Manager as a
# write-only argument, so it is never written to the Terraform state or plan.

ephemeral "random_password" "app" {
  length           = 24
  min_upper        = 2
  min_lower        = 2
  min_numeric      = 2
  min_special      = 2
  override_special = "!#%*-_=+:.?" # no quotes or $, which would break the SQL literal or sqlcmd variables
}

resource "aws_secretsmanager_secret" "app" {
  #checkov:skip=CKV_AWS_149:The AWS managed key encrypts the secret; a customer managed key is listed under production changes.
  #checkov:skip=CKV2_AWS_57:Rotating the app login needs a rotation function; it is listed under production changes.
  name_prefix             = "tesa-m11/squad-app-"
  description             = "Password of the squad_app SQL Server login"
  recovery_window_in_days = 0 # deleted at once on destroy, so the lab leaves nothing behind
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id                = aws_secretsmanager_secret.app.id
  secret_string_wo         = ephemeral.random_password.app.result
  secret_string_wo_version = 1 # raise to store a new password
}
