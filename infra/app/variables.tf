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

variable "notification_email" {
  description = "My email. Sent in the USAJobs User-Agent header and used for the SNS subscriptions. Comes from a gitignored terraform.tfvars locally, or the NOTIFICATION_EMAIL repo secret in CI."
  type        = string
  sensitive   = true

  # A missing repo secret arrives as an empty string. Fail the plan instead
  # of deploying a Lambda with no contact email.
  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.notification_email))
    error_message = "notification_email must be a valid email address. Check the NOTIFICATION_EMAIL secret or terraform.tfvars."
  }
}
