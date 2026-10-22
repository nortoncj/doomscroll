###############################################################################
# Status API: PATCH /jobs/{job_id} -> update_status Lambda -> DynamoDB
#
# HTTP API with IAM (SigV4) auth. API Gateway rejects unsigned requests with
# a 403 before the Lambda runs. Only identities in this account with
# execute-api:Invoke can call it, which in practice means my SSO role.
# Call it with awscurl.
###############################################################################

locals {
  update_status_name = "${var.name_prefix}-update-status"
  update_status_src  = "${path.module}/../../src/update_status"
}

# ---------------------------------------------------------------------------
# update_status Lambda
# ---------------------------------------------------------------------------

data "archive_file" "update_status" {
  type        = "zip"
  output_path = "${path.module}/build/update_status.zip"

  dynamic "source" {
    for_each = fileset(local.update_status_src, "*.py")
    content {
      content  = file("${local.update_status_src}/${source.value}")
      filename = source.value
    }
  }
}

resource "aws_cloudwatch_log_group" "update_status" {
  #checkov:skip=CKV_AWS_158:Logs hold job IDs and statuses, no secrets. A customer managed KMS key costs $1/month for no real gain.
  #checkov:skip=CKV_AWS_338:14 day retention is intentional. These are debug logs for a personal tool, not audit records.
  name              = "/aws/lambda/${local.update_status_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "update_status" {
  #checkov:skip=CKV_AWS_117:Only talks to DynamoDB. A VPC would add endpoints or a NAT gateway for no security gain.
  #checkov:skip=CKV_AWS_116:Invoked synchronously by API Gateway. Errors go straight back to the caller, so a DLQ would never receive anything.
  #checkov:skip=CKV_AWS_115:Reserved concurrency fails on new accounts with a 10 execution limit. Stage throttling caps traffic instead.
  #checkov:skip=CKV_AWS_173:The only environment variable is the table name.
  #checkov:skip=CKV_AWS_272:Code is built and deployed only by the CI apply role from reviewed commits on main.
  #checkov:skip=CKV_AWS_50:X-Ray tracing isn't needed for a handful of manual calls a day. Structured logs cover debugging.
  function_name    = local.update_status_name
  description      = "PATCH /jobs/{job_id}: validates and updates a job's status."
  role             = aws_iam_role.update_status.arn
  runtime          = "python3.12"
  handler          = "update_status.lambda_handler"
  filename         = data.archive_file.update_status.output_path
  source_code_hash = data.archive_file.update_status.output_base64sha256
  memory_size      = 128
  timeout          = 10

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.jobs.name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.update_status,
    aws_iam_role_policy.update_status,
  ]
}

# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "jobs" {
  name          = "${var.name_prefix}-api"
  description   = "Job status updates. IAM auth only."
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "update_status" {
  api_id                 = aws_apigatewayv2_api.jobs.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.update_status.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "patch_job" {
  api_id             = aws_apigatewayv2_api.jobs.id
  route_key          = "PATCH /jobs/{job_id}"
  authorization_type = "AWS_IAM"
  target             = "integrations/${aws_apigatewayv2_integration.update_status.id}"
}

resource "aws_cloudwatch_log_group" "api_access" {
  #checkov:skip=CKV_AWS_158:Access logs hold request metadata, no secrets. A customer managed KMS key costs $1/month for no real gain.
  #checkov:skip=CKV_AWS_338:14 day retention is intentional for a personal tool.
  name              = "/aws/apigateway/${var.name_prefix}-api"
  retention_in_days = 14
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.jobs.id
  name        = "$default"
  auto_deploy = true

  # Low limits on purpose. It's one person clicking through a digest, and a
  # leaked or looping script can't run up a bill.
  default_route_settings {
    throttling_burst_limit = 10
    throttling_rate_limit  = 5
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId = "$context.requestId"
      caller    = "$context.identity.userArn"
      route     = "$context.routeKey"
      status    = "$context.status"
      error     = "$context.error.message"
      latencyMs = "$context.responseLatency"
    })
  }
}

# Let this API, and only this route, invoke the Lambda.
resource "aws_lambda_permission" "api_invoke_update_status" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.update_status.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.jobs.execution_arn}/*/PATCH/jobs/*"
}
