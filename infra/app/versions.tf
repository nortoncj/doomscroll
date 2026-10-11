terraform {
  required_version = ">= 1.11.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    # Zips the Lambda code at plan time.
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}
