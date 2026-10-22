###############################################################################
# SNS: two topics so alerts never get buried under digests.
#
# Both email subscriptions start as "PendingConfirmation". Click the link in
# each AWS email. Terraform can't click it for you, and an unconfirmed
# subscription can't be deleted by destroy (it ages out after 3 days).
###############################################################################

resource "aws_sns_topic" "job_digest" {
  #checkov:skip=CKV_AWS_26:Digest carries public job listings only. A customer managed KMS key costs $1/month (20% of the budget) to protect public data.
  name = "${var.name_prefix}-job-digest"
}

resource "aws_sns_topic_subscription" "job_digest_email" {
  topic_arn = aws_sns_topic.job_digest.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

resource "aws_sns_topic" "job_alerts" {
  #checkov:skip=CKV_AWS_26:CloudWatch alarms can't publish to a topic encrypted with the AWS managed aws/sns key, and a customer managed key costs $1/month to protect alarm names.
  name = "${var.name_prefix}-job-alerts"
}

resource "aws_sns_topic_subscription" "job_alerts_email" {
  topic_arn = aws_sns_topic.job_alerts.arn
  protocol  = "email"
  endpoint  = var.notification_email
}
