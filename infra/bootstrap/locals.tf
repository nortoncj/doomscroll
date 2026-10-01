# Who am I? Pulls the account ID from whatever credentials ran the apply,
# so nothing account specific is hardcoded in the repo.
data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = var.aws_region
  prefix     = var.name_prefix

  # S3 bucket names are global across ALL of AWS. Adding the account ID
  # makes a collision basically impossible.
  state_bucket_name = "${var.name_prefix}-tfstate-${local.account_id}"

  # GitHub's sub claim uses immutable IDs: repo:OWNER@OWNER_ID/REPO@REPO_ID
  github_repo_sub = "repo:${var.github_owner}@${var.github_owner_id}/${var.github_repo}@${var.github_repo_id}"
}