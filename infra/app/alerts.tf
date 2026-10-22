###############################################################################
# Alarm and budget
###############################################################################

# Any fetch_jobs error in a day emails me. The handler raises at the end of
# a run when a source or the digest failed, so this catches both.
# No data (no invocations) counts as fine, so quiet days don't false alarm.
resource "aws_cloudwatch_metric_alarm" "fetch_jobs_errors" {
  alarm_name          = "${var.name_prefix}-fetch-jobs-errors"
  alarm_description   = "fetch_jobs reported an error in the last day. Check its CloudWatch logs."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.fetch_jobs.function_name }
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.job_alerts.arn]
}

# Whole account, not just this project. On a personal account that's what
# I actually want to know about. Budgets data lags several hours, so this
# catches slow cost creep. The alarm above catches broken runs.
resource "aws_budgets_budget" "monthly" {
  name         = "${var.name_prefix}-monthly"
  budget_type  = "COST"
  limit_amount = "5"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.notification_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.notification_email]
  }
}
