provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "TESA-Cloud-Engineering"
      Module    = "13-iac-cicd"
      ManagedBy = "Terraform, GitHub Actions"
    }
  }
}
