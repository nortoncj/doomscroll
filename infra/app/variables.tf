variable "aws_region" {
  description = "Region for every resource in the app stack."
  type        = string
  default     = "us-east-1"
}

variable "name_prefix" {
  description = "Every resource name starts with this. The CI apply role is scoped to it, so don't change it."
  type        = string
  default     = "doomscroll"
}

variable "usajobs_email" {
  description = "Email registered with the USAJobs API. Sent in the User-Agent header. Public, not a secret."
  type        = string
  default     = "contact@chrisnortonjr.com"
}