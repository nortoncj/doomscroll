###############################################################################
# Daily schedule: 6:00 AM Eastern
#
# EventBridge Scheduler handles daylight saving time on its own because the
# timezone is set, so 6 AM stays 6 AM in November and March.
###############################################################################

data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    # Confused deputy protection: only schedules in THIS account can use the role.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name                 = "${var.name_prefix}-scheduler"
  description          = "Lets EventBridge Scheduler invoke the fetch Lambda."
  assume_role_policy   = data.aws_iam_policy_document.scheduler_trust.json
  permissions_boundary = local.boundary_arn
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "InvokeFetchJobs"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.fetch_jobs.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "invoke-fetch-jobs"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "fetch_jobs_daily" {
  #checkov:skip=CKV_AWS_297:The schedule payload is an empty event with no data. A customer managed KMS key costs $1/month for no real gain.
  name        = "${var.name_prefix}-fetch-jobs-daily"
  description = "Run the job fetch every morning."

  schedule_expression          = "cron(0 6 * * ? *)"
  schedule_expression_timezone = "America/New_York"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.fetch_jobs.arn
    role_arn = aws_iam_role.scheduler.arn

    # Only covers failures to *start* the Lambda (like throttling).
    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }

  depends_on = [aws_iam_role_policy.scheduler]
}

# Scheduler invokes Lambda asynchronously, and async invokes retry a failed
# run twice by default. Our run already retries each source internally and
# raises on purpose when a source is down, so a full rerun would just hammer
# the same broken API. One run per morning, and the alarm (M3) handles the rest.
resource "aws_lambda_function_event_invoke_config" "fetch_jobs" {
  function_name          = aws_lambda_function.fetch_jobs.function_name
  maximum_retry_attempts = 0
}
