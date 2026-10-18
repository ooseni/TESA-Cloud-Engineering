variable "region" {
  description = "Region for the run. The design targets af-south-1 (ADR-0005, proposed); this account runs its labs in Europe (London), and nothing in the run depends on the Region."
  type        = string
  default     = "eu-west-2"
}

variable "availability_zones" {
  description = "Two zones: Amazon MSK needs its brokers spread across at least two."
  type        = list(string)
  default     = ["eu-west-2a", "eu-west-2b"]

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "Give exactly two zones; the subnets and brokers are laid out for two."
  }
}

variable "vpc_cidr" {
  description = "The VPC's range, as in the design's network page."
  type        = string
  default     = "10.40.0.0/16"
}

variable "kafka_version" {
  description = "Amazon MSK's Kafka version: the same 3.9 line as the demo's broker. MSK offers kafka.t3.small only for ZooKeeper-based clusters, not KRaft (3.9.x.kraft); clients see the same protocol."
  type        = string
  default     = "3.9.x"
}

variable "broker_instance_type" {
  description = "The smallest broker size; the design's production size is kafka.m7g.large."
  type        = string
  default     = "kafka.t3.small"
}

variable "host_instance_type" {
  description = "The test host runs the gateway, vendor mock, re-query worker, sync consumer and PostgreSQL in Docker, and the tests."
  type        = string
  default     = "t3.medium"
}

variable "bundle_dir" {
  description = "Where ../bundle.sh writes demo.zip and relay.zip."
  type        = string
  default     = "../dist"
}
