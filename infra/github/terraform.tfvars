project               = "njoagleod-api"
github_subject_prefix = "REPLACE_WITH_REPO_ID" # gh api repos/tor-gu/njoagleod-api/actions/oidc/customization/sub

envs = {
  dev = {
    stack_name      = "NjoagleodApiDev"
    distribution_id = "E1J4ZXO8DVB64P" # test-api.tor-gu.com
  }
  prod = {
    stack_name      = "NjoagleodApi"
    distribution_id = "E1769VXNMM34EW" # api.tor-gu.com
  }
}

cfn_execution_role_arn = "arn:aws:iam::490461464130:role/aws-sam-cli-managed-prod-CloudFormationExecutionR-Q7T0TM3BM99D"
sam_artifact_bucket    = "aws-sam-cli-managed-prod-pipeline-artifactsbucket-lshck0q70sdj"
torguapi_layer_name    = "layer_torguapi"
