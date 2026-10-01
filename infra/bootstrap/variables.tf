variable "aws_region" {
  description = "Region for the state bucket and everything the app stack builds."
  type        = string
  default     = "us-east-1"
}

variable "github_owner" {
  description = "GitHub user or org that owns the repo. Used in the OIDC trust policies."
  type        = string
  default     = "nortoncj"
}

variable "github_repo" {
  description = "GitHub repo name. Used in the OIDC trust policies."
  type        = string
  default     = "doomscroll"
}

variable "github_owner_id" {
  description = "Numeric GitHub user ID. GitHub includes it in the OIDC sub claim so a deleted or renamed account can't be impersonated."
  type        = string
  default     = "42925846"
}

variable "github_repo_id" {
  description = "Numeric GitHub repo ID. Same reason: a recreated repo with the same name gets a new ID and can't assume these roles."
  type        = string
  default     = "1391422537"
}

variable "name_prefix" {
  description = <<-EOT
    Every app stack resource must start with this prefix (doomscroll-jobs,
    doomscroll-fetch-jobs, etc). The CI apply role is only allowed to touch
    resources whose names match it. Change this and you break least privilege.
  EOT
  type        = string
  default     = "doomscroll"
}
