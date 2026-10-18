provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "TESA-Cloud-Engineering"
      Module    = "14-capstone-payments-gateway"
      Purpose   = "Short live run of the demo: destroyed after testing" # tag values allow only _ . : / = + - @
      ManagedBy = "Terraform"
    }
  }
}
