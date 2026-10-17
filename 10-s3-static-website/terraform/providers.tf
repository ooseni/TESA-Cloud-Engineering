provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "TESA-Cloud-Engineering"
      Module    = "10-s3-static-website"
      ManagedBy = "Terraform"
    }
  }
}
