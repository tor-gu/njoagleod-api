output "readonly_role_arn" {
  value = aws_iam_role.readonly.arn
}

output "deploy_role_arns" {
  value = { for env, role in aws_iam_role.deploy : env => role.arn }
}
