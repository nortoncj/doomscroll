###############################################################################
# IAM for the app's Lambdas
#
# Every role here MUST:
#   1. Be named doomscroll-*        (the CI apply role is scoped to that prefix)
#   2. Carry the workload boundary  (the apply role can't create a role without it)
#
# Skip either one and the deploy fails with AccessDenied. That's the guardrail
# from bootstrap doing its job, not a bug.
###############################################################################

data "aws_caller_identity" "current" {}

locals {
  account_id   = data.aws_caller_identity.current.account_id
  boundary_arn = "arn:aws:iam::${local.account_id}:policy/${var.name_prefix}-workload-boundary"
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# ---------------------------------------------------------------------------
# fetch_jobs
# ---------------------------------------------------------------------------

resource "aws_iam_role" "fetch_jobs" {
  name                 = "${var.name_prefix}-fetch-jobs"
  description          = "Runtime role for the daily job fetch Lambda."
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = local.boundary_arn
}

data "aws_iam_policy_document" "fetch_jobs" {
  #checkov:skip=CKV_AWS_356:kms:Decrypt is locked to SSM via kms:ViaService. The AWS managed key ARN isn't known ahead of time.

  # Insert new jobs only. No reads, no updates, no deletes.
  statement {
    sid       = "InsertJobs"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.jobs.arn]
  }

  # Exactly the three API key parameters. Nothing else in SSM.
  statement {
    sid       = "ReadApiKeys"
    actions   = ["ssm:GetParameter"]
    resources = [for p in aws_ssm_parameter.api : p.arn]
  }

  # SecureString values are encrypted with aws/ssm. Decrypt only through SSM.
  statement {
    sid       = "DecryptApiKeysViaSSM"
    actions   = ["kms:Decrypt"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }

  # Publish the digest. Only this one topic.
  statement {
    sid       = "PublishDigest"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.job_digest.arn]
  }

  # Write to its own log group. Terraform creates the group, so no
  # logs:CreateLogGroup here.
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.fetch_jobs.arn}:*"]
  }
}

resource "aws_iam_role_policy" "fetch_jobs" {
  name   = "fetch-jobs-runtime"
  role   = aws_iam_role.fetch_jobs.id
  policy = data.aws_iam_policy_document.fetch_jobs.json
}

# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------

resource "aws_iam_role" "update_status" {
  name                 = "${var.name_prefix}-update-status"
  description          = "Runtime role for the status update API Lambda."
  assume_role_policy   = data.aws_iam_policy_document.lambda_trust.json
  permissions_boundary = local.boundary_arn
}

data "aws_iam_policy_document" "update_status" {
  # Update existing jobs only. The conditional update in code means it can
  # never create one, and it can't read, insert, or delete.
  statement {
    sid       = "UpdateJobs"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.jobs.arn]
  }

  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.update_status.arn}:*"]
  }
}

resource "aws_iam_role_policy" "update_status" {
  name   = "update-status-runtime"
  role   = aws_iam_role.update_status.id
  policy = data.aws_iam_policy_document.update_status.json
}
