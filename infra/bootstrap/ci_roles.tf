###############################################################################
# CI roles
#
# Two roles, two jobs:
#   ci-doomscroll-plan   PRs only. Can look at everything, change nothing.
#   ci-doomscroll-apply  main branch only. Can change only doomscroll-* stuff.
#
# Unreviewed PR code can never deploy. Only merged code can.
#
# Naming note: these roles start with "ci-", NOT "doomscroll-". That's on
# purpose. The apply role can manage roles named doomscroll-*, so if the CI
# roles matched that prefix, the apply role could edit itself.
#
# Heads up: if a workflow ever uses a GitHub "environment:", the token's sub
# changes to repo:OWNER/REPO:environment:NAME and these trust policies will
# reject it. Update the sub values if you add environments.
###############################################################################

# ---------------------------------------------------------------------------
# Trust policies (the bouncer: WHO can assume each role)
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ci_plan_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    # Token must be meant for AWS.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Token must come from a pull request in THIS repo. Nothing else.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.github_repo_sub}:pull_request"]
    }
  }
}

data "aws_iam_policy_document" "ci_apply_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Token must come from the main branch of THIS repo. Nothing else.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.github_repo_sub}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "ci_plan" {
  name                 = "ci-${local.prefix}-plan"
  description          = "GitHub Actions: terraform plan on pull requests. Read only."
  assume_role_policy   = data.aws_iam_policy_document.ci_plan_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role" "ci_apply" {
  name                 = "ci-${local.prefix}-apply"
  description          = "GitHub Actions: terraform apply on main. Scoped to doomscroll-* resources."
  assume_role_policy   = data.aws_iam_policy_document.ci_apply_trust.json
  max_session_duration = 3600
}

# ---------------------------------------------------------------------------
# State access (both roles need it)
#
# Plan is "read only" but still has to WRITE the .tflock file, because
# S3 native locking works by creating a lock object next to the state file.
# ReadOnlyAccess alone fails on the very first plan.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "state_access" {
  statement {
    sid       = "ListStateBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
  }

  statement {
    sid       = "ReadState"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.state.arn}/*"]
  }

  statement {
    sid       = "ManageLockFile"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/*.tflock"]
  }
}

resource "aws_iam_role_policy" "ci_plan_state" {
  name   = "state-access"
  role   = aws_iam_role.ci_plan.id
  policy = data.aws_iam_policy_document.state_access.json
}

resource "aws_iam_role_policy" "ci_apply_state" {
  name   = "state-access"
  role   = aws_iam_role.ci_apply.id
  policy = data.aws_iam_policy_document.state_access.json
}

# ---------------------------------------------------------------------------
# Plan role permissions: look, don't touch.
# ---------------------------------------------------------------------------

resource "aws_iam_role_policy_attachment" "ci_plan_readonly" {
  role       = aws_iam_role.ci_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}
