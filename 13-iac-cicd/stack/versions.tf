terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.60"
    }
  }

  # Remote state. bucket, key and region come from -backend-config at init (from the repository's
  # Actions variables), so no account-specific name is written in the code.
  backend "s3" {
    use_lockfile = true # S3 native locking: a .tflock object beside the state, no DynamoDB table
    encrypt      = true
  }
}
