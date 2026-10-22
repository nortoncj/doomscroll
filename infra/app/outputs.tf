output "jobs_table_name" {
  value = aws_dynamodb_table.jobs.name
}

output "jobs_table_arn" {
  value = aws_dynamodb_table.jobs.arn
}

output "fetch_jobs_function_name" {
  value = aws_lambda_function.fetch_jobs.function_name
}


output "digest_topic_arn" {
  value = aws_sns_topic.job_digest.arn
}

output "alerts_topic_arn" {
  value = aws_sns_topic.job_alerts.arn
}
