variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  description = "Prefix for the role names"
  type        = string
}

variable "github_subject_prefix" {
  description = <<-EOT
    Start of the OIDC sub claim of the repository whose workflows may assume
    the roles: gh api repos/<owner>/<repo>/actions/oidc/customization/sub
    shows it as sub_claim_prefix (repo:<owner>@<id>/<repo>@<id> for immutable
    subjects)
  EOT
  type        = string
}

variable "envs" {
  description = "Deploy environments, keyed by GitHub environment name (prod deploys from main, dev from dev)"
  type = map(object({
    stack_name      = string # the SAM stack
    distribution_id = string # the CloudFront distribution whose cache the deploy clears
  }))
}

variable "cfn_execution_role_arn" {
  description = "Role CloudFormation assumes for sam deploy (shared with other SAM projects)"
  type        = string
}

variable "sam_artifact_bucket" {
  description = "Bucket sam deploy uploads packaged code to (shared with other SAM projects)"
  type        = string
}

variable "torguapi_layer_name" {
  description = "Name of the torguapi Lambda layer, which the unit tests download"
  type        = string
}
