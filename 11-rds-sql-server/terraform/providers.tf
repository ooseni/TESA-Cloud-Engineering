provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "TESA-Cloud-Engineering"
      Module    = "11-rds-sql-server"
      ManagedBy = "Terraform"
    }
  }
}
