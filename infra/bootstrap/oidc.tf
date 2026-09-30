###############################################################################
# GitHub OIDC provider
#
# Tells AWS: "tokens signed by GitHub Actions are legit." Grants zero
# permissions by itself. It only lets AWS verify who is knocking. The roles
# in ci_roles.tf decide who actually gets in.
#
# One per AWS account. If it already exists from another project, import it
# instead of creating a second one:
#   terraform import aws_iam_openid_connect_provider.github \
#     arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com
###############################################################################

resource "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"

  # The "audience" GitHub stamps on tokens meant for AWS.
  client_id_list = ["sts.amazonaws.com"]

  # No thumbprint_list. AWS validates GitHub's certificate on its own now,
  # and the provider no longer requires it.
}
