# Amazon RDS for SQL Server Express: private, encrypted, TLS enforced, master password managed by RDS
# in AWS Secrets Manager and rotated, with backups and Enhanced Monitoring.

resource "aws_db_subnet_group" "db" {
  name        = "tesa-m11-db"
  description = "The two private subnets"
  subnet_ids  = aws_subnet.private[*].id
}

# rds.force_ssl makes the server encrypt every connection, even when a client does not ask.
resource "aws_db_parameter_group" "db" {
  name        = "tesa-m11-sqlserver-ex-16"
  family      = "sqlserver-ex-16.0"
  description = "Force TLS on every connection"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }
}

data "aws_iam_policy_document" "monitoring_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "monitoring" {
  name               = "tesa-m11-rds-monitoring"
  assume_role_policy = data.aws_iam_policy_document.monitoring_assume.json
}

resource "aws_iam_role_policy_attachment" "monitoring" {
  role       = aws_iam_role.monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

resource "aws_db_instance" "db" {
  #checkov:skip=CKV_AWS_157:SQL Server Express does not support Multi-AZ; Standard edition with Multi-AZ is listed under production changes.
  #checkov:skip=CKV_AWS_161:RDS for SQL Server does not support IAM database authentication; Kerberos through AWS Managed Microsoft AD is the alternative.
  #checkov:skip=CKV_AWS_293:Deletion protection is a variable, off only so this lab can be torn down.
  #checkov:skip=CKV_AWS_353:Performance Insights is not available for this instance class.
  #checkov:skip=CKV_AWS_354:Follows from CKV_AWS_353.
  identifier     = "tesa-m11-sqlserver"
  engine         = "sqlserver-ex"
  engine_version = var.engine_version
  license_model  = "license-included"
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  username                    = "dbadmin"
  manage_master_user_password = true # RDS keeps the password in Secrets Manager and rotates it

  db_subnet_group_name   = aws_db_subnet_group.db.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = false
  parameter_group_name   = aws_db_parameter_group.db.name
  ca_cert_identifier     = "rds-ca-rsa2048-g1"

  backup_retention_period    = var.backup_retention_days
  backup_window              = "02:00-03:00"
  maintenance_window         = "sun:03:30-sun:04:30"
  copy_tags_to_snapshot      = true
  auto_minor_version_upgrade = true
  deletion_protection        = var.deletion_protection
  skip_final_snapshot        = var.skip_final_snapshot
  final_snapshot_identifier  = "tesa-m11-sqlserver-final"

  enabled_cloudwatch_logs_exports = ["error"]
  monitoring_interval             = 60
  monitoring_role_arn             = aws_iam_role.monitoring.arn

  apply_immediately = true

  depends_on = [aws_iam_role_policy_attachment.monitoring]
}
