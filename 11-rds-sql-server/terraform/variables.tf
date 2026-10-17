variable "region" {
  description = "AWS Region."
  type        = string
  default     = "eu-west-1"
}

variable "vpc_cidr" {
  description = "Address range of the isolated VPC."
  type        = string
  default     = "10.90.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "Use an IPv4 CIDR block such as 10.90.0.0/16."
  }
}

variable "availability_zones" {
  description = "The two zones for the DB subnet group. Pinned, so the network never changes when AWS adds a zone."
  type        = list(string)
  default     = ["eu-west-1a", "eu-west-1b"]

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "Give exactly two zones: a DB subnet group needs subnets in at least two."
  }
}

variable "engine_version" {
  description = "SQL Server Express version. 16.00 is SQL Server 2022, the same major version as the CI container."
  type        = string
  default     = "16.00.4295.3.v1"
}

variable "instance_class" {
  description = "Instance class. db.t3.micro is the smallest class that runs SQL Server Express."
  type        = string
  default     = "db.t3.micro"
}

variable "allocated_storage" {
  description = "Initial storage in GiB (20 is the minimum for SQL Server Express)."
  type        = number
  default     = 20
}

variable "max_allocated_storage" {
  description = "Storage autoscaling ceiling in GiB."
  type        = number
  default     = 100
}

variable "backup_retention_days" {
  description = "Days of automated backups and point-in-time recovery."
  type        = number
  default     = 7

  validation {
    condition     = var.backup_retention_days >= 1 && var.backup_retention_days <= 35
    error_message = "Use 1 to 35 days; 0 would turn backups off."
  }
}

variable "deletion_protection" {
  description = "Refuse deletion. false only so this lab can be torn down; true in production."
  type        = bool
  default     = false
}

variable "skip_final_snapshot" {
  description = "Skip the snapshot on deletion. true only for this lab; false in production."
  type        = bool
  default     = true
}
