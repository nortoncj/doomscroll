###############################################################################
# API keys for the job sources
#
# Terraform creates each parameter with a placeholder, then ignores the value
# forever. You set the real value once from your laptop:
#
#   aws ssm put-parameter --name /doomscroll/usajobs/api_key \
#     --type SecureString --overwrite --value "<key>"
#
# Real values never touch git. Honest caveat: Terraform reads the current
# value into state on refresh, so state holds it. That's why the state bucket
# is private, encrypted, and versioned.
###############################################################################

locals {
  api_parameters = {
    usajobs_api_key = "usajobs/api_key"
    adzuna_app_id   = "adzuna/app_id"
    adzuna_app_key  = "adzuna/app_key"
  }
}

resource "aws_ssm_parameter" "api" {
  #checkov:skip=CKV_AWS_337:Encrypted with the AWS managed aws/ssm key. A customer managed KMS key costs $1/month for no real gain here.
  for_each = local.api_parameters

  name        = "/${var.name_prefix}/${each.value}"
  description = "Doomscroll job source credential. Real value set by hand, never in git."
  type        = "SecureString"
  value       = "CHANGE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

# The parameters were created by hand before the first deploy finished.
# Adopt them into state instead of recreating them. ignore_changes on the
# resource means the real key values stay exactly as they are.
import {
  for_each = local.api_parameters
  to       = aws_ssm_parameter.api[each.key]
  id       = "/${var.name_prefix}/${each.value}"
}
