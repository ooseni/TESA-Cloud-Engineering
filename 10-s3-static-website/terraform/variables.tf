variable "region" {
  description = "AWS Region for the bucket. CloudFront itself is global."
  type        = string
  default     = "eu-west-1"
}

variable "name_prefix" {
  description = "Start of the bucket name. AWS adds a unique suffix, so no account ID appears in any name or URL."
  type        = string
  default     = "tesa-m10-site-"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,35}$", var.name_prefix))
    error_message = "Use 3 to 36 lowercase letters, digits and hyphens."
  }
}

variable "price_class" {
  description = "CloudFront price class. PriceClass_100 serves from North America and Europe only, the cheapest."
  type        = string
  default     = "PriceClass_100"

  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.price_class)
    error_message = "Use PriceClass_100, PriceClass_200 or PriceClass_All."
  }
}

variable "site_dir" {
  description = "Folder whose files are published to the bucket."
  type        = string
  default     = "../site"
}
