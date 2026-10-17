terraform {
  # 1.11 or later: the app login's password is sent to Secrets Manager as a write-only value, never stored in state
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.60"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }
}
