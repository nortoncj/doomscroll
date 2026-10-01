resource "aws_dynamodb_table" "jobs" {
  #checkov:skip=CKV_AWS_119:AWS owned key encryption is on by default. A customer managed KMS key costs $1/month for no real gain here.
  name         = "${var.name_prefix}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  # Only attributes used as keys get declared here. DynamoDB is schemaless
  # for everything else (title, company, url, etc).
  attribute {
    name = "job_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "first_seen_at"
    type = "S"
  }

  # "Show me everything I've applied to, newest first."
  global_secondary_index {
    name            = "status-index"
    hash_key        = "status"
    range_key       = "first_seen_at"
    projection_type = "ALL"
  }

  # Continuous backups for 35 days. Costs pennies at this size and
  # checkov flags tables without it.
  point_in_time_recovery {
    enabled = true
  }


}