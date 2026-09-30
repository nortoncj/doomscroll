###############################################################################
# Terraform state bucket
#
# Terraform's memory of what exists in AWS. Lives in S3 so both your laptop
# and GitHub Actions read and write the same state.
###############################################################################

resource "aws_s3_bucket" "state" {
  #checkov:skip=CKV_AWS_18:Access logging needs a second bucket. Overkill for a single user state bucket.
  #checkov:skip=CKV_AWS_144:Cross region replication doubles cost. Versioning covers recovery for this workload.
  #checkov:skip=CKV_AWS_145:SSE-S3 encryption is enabled. A customer managed KMS key costs $1/month for no real gain here.
  #checkov:skip=CKV2_AWS_62:Nothing needs to react to state file changes.
  bucket = local.state_bucket_name

  # Guardrail: Terraform refuses to destroy this bucket. Losing state means
  # Terraform forgets everything it built. Remove this line on purpose, never
  # by accident.
  lifecycle {
    prevent_destroy = true
  }
}

# Versioning = undo button. Every state write keeps the previous copy,
# so a corrupted or botched state file can be rolled back.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Encrypt at rest. State can contain sensitive values.
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block every form of public access. A public state bucket is how you end
# up as a cautionary tale on Reddit.
resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Old state versions pile up forever without this. Keep 90 days of history,
# then let S3 clean up. Also clears half finished uploads.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.state]
}

# Refuse any request that isn't over HTTPS.
data "aws_iam_policy_document" "state_tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state_tls_only.json

  # Public access block has to land first or the policy apply can race it.
  depends_on = [aws_s3_bucket_public_access_block.state]
}
