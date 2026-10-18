variable "region" {
  description = "Region of the state bucket and the stack. The original pipeline used Europe (London)."
  type        = string
  default     = "eu-west-2"
}

variable "github_repository" {
  description = "The only repository whose workflows may assume the roles, as owner/name."
  type        = string
  default     = "ooseni/TESA-Cloud-Engineering"

  validation {
    condition     = can(regex("^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$", var.github_repository))
    error_message = "Use the owner/name form, for example ooseni/TESA-Cloud-Engineering."
  }
}

# Repositories created after 15 July 2026 get immutable subject claims: the owner's and the repository's
# numeric IDs follow their names, so a deleted repository's name, reused, matches nothing. Read the prefix with:
#   gh api repos/OWNER/REPO/actions/oidc/customization/sub --jq .sub_claim_prefix
variable "github_subject_prefix" {
  description = "The start of the OIDC sub claim GitHub issues for the repository."
  type        = string
  default     = "repo:ooseni@61007256/TESA-Cloud-Engineering@1420014824"

  validation {
    condition     = can(regex("^repo:[A-Za-z0-9-]+(@[0-9]+)?/[A-Za-z0-9._-]+(@[0-9]+)?$", var.github_subject_prefix))
    error_message = "Use repo:OWNER@OWNER_ID/REPO@REPO_ID, or repo:OWNER/REPO for an older repository."
  }
}

variable "state_key" {
  description = "Object key of the stack's state file in the bucket."
  type        = string
  default     = "13-iac-cicd/stack.tfstate"
}

variable "force_destroy" {
  description = "Let terraform destroy empty the state bucket. true only so this lab can be removed."
  type        = bool
  default     = true
}
