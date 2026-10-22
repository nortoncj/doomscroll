###############################################################################
# fetch_jobs Lambda
#
# The zip is built at plan time from src/fetch_jobs/*.py plus
# config/filters.json (placed at the zip root, where filters.py looks for it).
# Code changes and infra changes ship through the same pipeline.
###############################################################################

locals {
  fetch_jobs_name = "${var.name_prefix}-fetch-jobs"
  fetch_jobs_src  = "${path.module}/../../src/fetch_jobs"
}

data "archive_file" "fetch_jobs" {
  type        = "zip"
  output_path = "${path.module}/build/fetch_jobs.zip"

  # Only .py files, so __pycache__ and local junk never ship.
  dynamic "source" {
    for_each = fileset(local.fetch_jobs_src, "*.py")
    content {
      content  = file("${local.fetch_jobs_src}/${source.value}")
      filename = source.value
    }
  }

  source {
    content  = file("${path.module}/../../config/filters.json")
    filename = "filters.json"
  }
}

resource "aws_cloudwatch_log_group" "fetch_jobs" {
  #checkov:skip=CKV_AWS_158:Logs hold job titles and counts, no secrets. A customer managed KMS key costs $1/month for no real gain.
  #checkov:skip=CKV_AWS_338:14 day retention is intentional. These are debug logs for a personal tool, not audit records.
  name              = "/aws/lambda/${local.fetch_jobs_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "fetch_jobs" {
  #checkov:skip=CKV_AWS_117:Only calls public HTTPS APIs, DynamoDB, and SSM. A VPC would add a NAT gateway (~$32/month) for no security gain.
  #checkov:skip=CKV_AWS_116:Runs on a schedule, not from a queue. Failures raise and trip the CloudWatch alarm (M3), and the next day's run retries.
  #checkov:skip=CKV_AWS_115:Reserved concurrency fails on new accounts with a 10 execution limit. One scheduled invocation per day can't run away.
  #checkov:skip=CKV_AWS_173:Environment variables hold a table name, an SSM path, and a public email. Secrets live in SSM.
  #checkov:skip=CKV_AWS_272:Code is built and deployed only by the CI apply role from reviewed commits on main. Code signing adds a signing profile for no extra protection here.
  #checkov:skip=CKV_AWS_50:X-Ray tracing isn't needed for a single daily invocation. Structured logs cover debugging.
  function_name    = local.fetch_jobs_name
  description      = "Daily job fetch: pulls 4 sources, filters, and inserts new matches."
  role             = aws_iam_role.fetch_jobs.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.fetch_jobs.output_path
  source_code_hash = data.archive_file.fetch_jobs.output_base64sha256
  memory_size      = 256
  timeout          = 300

  environment {
    variables = {
      TABLE_NAME    = aws_dynamodb_table.jobs.name
      SSM_PREFIX    = "/${var.name_prefix}"
      USAJOBS_EMAIL = var.notification_email

      DIGEST_TOPIC_ARN = aws_sns_topic.job_digest.arn
    }
  }

  # Log group first, so Lambda never auto-creates one with infinite retention.
  # Policy first, so the very first invoke already has permissions.
  depends_on = [
    aws_cloudwatch_log_group.fetch_jobs,
    aws_iam_role_policy.fetch_jobs,
  ]
}
