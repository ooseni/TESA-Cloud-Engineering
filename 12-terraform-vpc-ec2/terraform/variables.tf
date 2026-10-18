variable "region" {
  description = "AWS Region. The lab used Europe (London)."
  type        = string
  default     = "eu-west-2"
}

variable "availability_zone" {
  description = "Zone for the public subnet. Pinned, so the network never moves."
  type        = string
  default     = "eu-west-2a"
}

variable "vpc_cidr" {
  description = "Address range of the VPC."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "Use an IPv4 CIDR block such as 10.0.0.0/16."
  }
}

variable "subnet_cidr" {
  description = "Address range of the public subnet; must sit inside vpc_cidr."
  type        = string
  default     = "10.0.1.0/24"

  validation {
    condition     = can(cidrnetmask(var.subnet_cidr))
    error_message = "Use an IPv4 CIDR block such as 10.0.1.0/24."
  }
}

variable "instance_type" {
  description = "EC2 instance type."
  type        = string
  default     = "t3.micro"
}
