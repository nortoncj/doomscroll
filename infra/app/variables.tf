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