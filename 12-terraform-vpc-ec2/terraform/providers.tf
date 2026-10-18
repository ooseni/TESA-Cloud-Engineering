# Tags are set once here instead of merged into every resource, as the lab did.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "TESA-Cloud-Engineering"
      Module    = "12-terraform-vpc-ec2"
      ManagedBy = "Terraform"
    }
  }
}
