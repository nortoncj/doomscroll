# You'll paste these into backend.tf and the GitHub workflows.

output "state_bucket_name" {
  description = "Put this in the backend block of both stacks."
  value       = aws_s3_bucket.state.bucket
}

output "ci_plan_role_arn" {
  description = "role-to-assume for pr.yml"
  value       = aws_iam_role.ci_plan.arn
}

output "ci_apply_role_arn" {
  description = "role-to-assume for deploy.yml"
  value       = aws_iam_role.ci_apply.arn
}

output "workload_boundary_arn" {
  description = "Every IAM role in the app stack must set permissions_boundary to this."
  value       = aws_iam_policy.workload_boundary.arn
}
