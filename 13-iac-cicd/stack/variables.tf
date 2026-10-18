variable "region" {
  description = "AWS Region; must match the apply role's Region condition."
  type        = string
  default     = "eu-west-2"
}

variable "availability_zone" {
  description = "Zone for the public subnet. Pinned instead of derived from the Region name."
  type        = string
  default     = "eu-west-2a"
}

variable "vpc_cidr" {
  description = "Address range of the VPC."
  type        = string
  default     = "10.13.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "Use an IPv4 CIDR block such as 10.13.0.0/16."
  }
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "t3.micro"
}
