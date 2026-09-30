###############################################################################
# Apply role permissions
#
# Two layers:
#
# 1. Name scoping. The apply role can only touch resources named doomscroll-*
#    (tables, functions, topics, etc). It can't wander into anything else in
#    the account.
#
# 2. Permissions boundary. The apply role creates IAM roles for the Lambdas.
#    Without a guardrail, it could create a role with full admin and escalate.
#    So every role it creates MUST carry the boundary below, which caps what
#    that role can ever do, no matter what policy gets attached to it.
###############################################################################

locals {
  arn_prefix = {
    dynamodb  = "arn:aws:dynamodb:${local.region}:${local.account_id}:table/${local.prefix}-*"
    lambda    = "arn:aws:lambda:${local.region}:${local.account_id}:function:${local.prefix}-*"
    sns       = "arn:aws:sns:${local.region}:${local.account_id}:${local.prefix}-*"
    ssm       = "arn:aws:ssm:${local.region}:${local.account_id}:parameter/${local.prefix}/*"
    logs      = "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${local.prefix}-*"
    alarm     = "arn:aws:cloudwatch:${local.region}:${local.account_id}:alarm:${local.prefix}-*"
    scheduler = "arn:aws:scheduler:${local.region}:${local.account_id}:schedule/*/${local.prefix}-*"
    budget    = "arn:aws:budgets::${local.account_id}:budget/${local.prefix}-*"
    role      = "arn:aws:iam::${local.account_id}:role/${local.prefix}-*"
  }
}

# ---------------------------------------------------------------------------
# Permissions boundary: the ceiling for every role the app stack creates.
# A boundary grants nothing by itself. It only limits.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "workload_boundary" {
  #checkov:skip=CKV_AWS_356:kms:Decrypt is locked to SSM via kms:ViaService. The AWS managed key ARN isn't known ahead of time.

  statement {
    sid     = "DynamoDBJobsTable"
    actions = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"]
    resources = [
      local.arn_prefix.dynamodb,
      "${local.arn_prefix.dynamodb}/index/*",
    ]
  }

  statement {
    sid       = "ReadAppSecrets"
    actions   = ["ssm:GetParameter"]
    resources = [local.arn_prefix.ssm]
  }

  # SecureString parameters are encrypted with the aws/ssm KMS key.
  statement {
    sid       = "DecryptViaSSMOnly"
    actions   = ["kms:Decrypt"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${local.region}.amazonaws.com"]
    }
  }

  statement {
    sid       = "PublishNotifications"
    actions   = ["sns:Publish"]
    resources = [local.arn_prefix.sns]
  }

  statement {
    sid       = "WriteLambdaLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${local.arn_prefix.logs}:*"]
  }

  # Lets the EventBridge Scheduler role invoke the fetch Lambda.
  statement {
    sid       = "InvokeAppFunctions"
    actions   = ["lambda:InvokeFunction"]
    resources = [local.arn_prefix.lambda]
  }
}

resource "aws_iam_policy" "workload_boundary" {
  name        = "${local.prefix}-workload-boundary"
  description = "Permissions boundary for every IAM role the doomscroll app stack creates."
  policy      = data.aws_iam_policy_document.workload_boundary.json
}

# ---------------------------------------------------------------------------
# What the apply role can do
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ci_apply" {

  statement {
    sid     = "DynamoDB"
    actions = ["dynamodb:*"]
    resources = [
      local.arn_prefix.dynamodb,
      "${local.arn_prefix.dynamodb}/index/*",
    ]
  }

  statement {
    sid       = "Lambda"
    actions   = ["lambda:*"]
    resources = [local.arn_prefix.lambda]
  }

  statement {
    sid       = "SNS"
    actions   = ["sns:*"]
    resources = [local.arn_prefix.sns]
  }

  statement {
    sid       = "Scheduler"
    actions   = ["scheduler:*"]
    resources = [local.arn_prefix.scheduler]
  }

  # HTTP APIs are identified by random IDs, not names, so this one can only
  # be scoped to the region.
  statement {
    sid     = "APIGateway"
    actions = ["apigateway:GET", "apigateway:POST", "apigateway:PUT", "apigateway:PATCH", "apigateway:DELETE"]
    resources = [
      "arn:aws:apigateway:${local.region}::/apis",
      "arn:aws:apigateway:${local.region}::/apis/*",
      "arn:aws:apigateway:${local.region}::/tags/*",
    ]
  }

  statement {
    sid       = "SSMParameters"
    actions   = ["ssm:*"]
    resources = [local.arn_prefix.ssm]
  }

  statement {
    sid       = "LogGroups"
    actions   = ["logs:*"]
    resources = [local.arn_prefix.logs, "${local.arn_prefix.logs}:*"]
  }

  # These Describe calls don't support resource scoping. AWS requires "*".
  statement {
    sid       = "UnscopableDescribes"
    actions   = ["ssm:DescribeParameters", "logs:DescribeLogGroups"]
    resources = ["*"]
  }

  statement {
    sid = "Alarms"
    actions = [
      "cloudwatch:PutMetricAlarm",
      "cloudwatch:DeleteAlarms",
      "cloudwatch:DescribeAlarms",
      "cloudwatch:ListTagsForResource",
      "cloudwatch:TagResource",
      "cloudwatch:UntagResource",
    ]
    resources = [local.arn_prefix.alarm]
  }

  statement {
    sid = "Budgets"
    actions = [
      "budgets:ViewBudget",
      "budgets:ModifyBudget",
      "budgets:ListTagsForResource",
      "budgets:TagResource",
      "budgets:UntagResource",
    ]
    resources = [local.arn_prefix.budget]
  }

  # Read and housekeeping on doomscroll-* roles. None of these grant new power.
  statement {
    sid = "IAMRoleHousekeeping"
    actions = [
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateRole",
      "iam:UpdateRoleDescription",
      "iam:UpdateAssumeRolePolicy",
      "iam:DeleteRole",
    ]
    resources = [local.arn_prefix.role]
  }

  # The escalation proof part. Creating a role or changing its permissions is
  # only allowed when the role carries the workload boundary.
  statement {
    sid = "IAMRoleWritesRequireBoundary"
    actions = [
      "iam:CreateRole",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePermissionsBoundary",
    ]
    resources = [local.arn_prefix.role]

    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [aws_iam_policy.workload_boundary.arn]
    }
  }

  # Lambda and Scheduler need to be handed a role. Only doomscroll-* roles,
  # and only to those two services.
  statement {
    sid       = "PassRoleToAppServices"
    actions   = ["iam:PassRole"]
    resources = [local.arn_prefix.role]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com", "scheduler.amazonaws.com"]
    }
  }

  # Terraform reads the boundary policy when it plans roles that use it.
  statement {
    sid       = "ReadBoundaryPolicy"
    actions   = ["iam:GetPolicy", "iam:GetPolicyVersion"]
    resources = [aws_iam_policy.workload_boundary.arn]
  }

  # Apply role needs to write the app state file itself, not just the lock.
  # Scoped to app/ so it can't overwrite bootstrap's state.
  statement {
    sid       = "WriteAppState"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.state.arn}/app/*"]
  }
}

resource "aws_iam_role_policy" "ci_apply" {
  name   = "app-stack-deploy"
  role   = aws_iam_role.ci_apply.id
  policy = data.aws_iam_policy_document.ci_apply.json
}
