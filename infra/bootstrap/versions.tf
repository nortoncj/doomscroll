# Pin Terraform and the AWS provider so every run (your laptop or CI)
# behaves the same way. 1.11+ is required for S3 native state locking.
terraform {
  required_version = ">= 1.11.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
