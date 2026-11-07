# IAM roles assumed by this repo's GitHub Actions workflow
# (.github/workflows/deploy.yml) through OIDC.
#
# The OIDC provider is account-wide and lives in the shared aws-infra repo.
# Each role trusts only tokens whose sub claim names this repo and either a
# branch (readonly) or a GitHub environment (deploy). The prod environment
# requires approval, so the prod deploy role is unusable until a run on main
# is approved.
#
# The repo has GitHub's immutable OIDC subjects, which name the owner and repo
# by id as well (repo:<owner>@<id>/<repo>@<id>), so the claim prefix is
# var.github_subject_prefix. New repos get these by default; the older
# njmunicipalities-api and layer_torguapi still have repo:<owner>/<repo>.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

locals {
  account = data.aws_caller_identity.current.account_id
  region  = data.aws_region.current.region

  oidc_host = "token.actions.githubusercontent.com"

  stack_arns = {
    for env, cfg in var.envs : env =>
    "arn:aws:cloudformation:${local.region}:${local.account}:stack/${cfg.stack_name}/*"
  }

  layer_arn = "arn:aws:lambda:${local.region}:${local.account}:layer:${var.torguapi_layer_name}:*"
}

# --- readonly ---
# Unit tests, the plan summary, integration tests. Any job on dev or main may
# use it, so it must not be able to change anything.

data "aws_iam_policy_document" "readonly_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values = [
        "${var.github_subject_prefix}:ref:refs/heads/dev",
        "${var.github_subject_prefix}:ref:refs/heads/main",
      ]
    }
  }
}

data "aws_iam_policy_document" "readonly" {
  statement {
    sid       = "FetchTorguapiLayer"
    actions   = ["lambda:GetLayerVersion"]
    resources = [local.layer_arn]
  }

  # The plan job reads the deployed stack's parameters; tests/integration
  # finds the API URL in the dev stack's outputs
  statement {
    sid       = "DescribeStacks"
    actions   = ["cloudformation:DescribeStacks"]
    resources = values(local.stack_arns)
  }
}

resource "aws_iam_role" "readonly" {
  name               = "${var.project}-gha-readonly"
  assume_role_policy = data.aws_iam_policy_document.readonly_trust.json
}

resource "aws_iam_role_policy" "readonly" {
  name   = "readonly"
  role   = aws_iam_role.readonly.id
  policy = data.aws_iam_policy_document.readonly.json
}

# --- deploy ---
# One role per environment: sam deploy, then clearing the CloudFront cache.

data "aws_iam_policy_document" "deploy_trust" {
  for_each = var.envs

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = ["${var.github_subject_prefix}:environment:${each.key}"]
    }
  }
}

data "aws_iam_policy_document" "deploy" {
  for_each = var.envs

  # sam deploy: CloudFormation does the work as cfn_execution_role_arn; this
  # role only uploads the code and drives the change set. Adapted from the
  # SAM-managed PipelineExecutionRole.
  statement {
    sid       = "SamPassRole"
    actions   = ["iam:PassRole"]
    resources = [var.cfn_execution_role_arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["cloudformation.amazonaws.com"]
    }
  }

  statement {
    sid = "SamStack"
    actions = [
      "cloudformation:CreateChangeSet",
      "cloudformation:DescribeChangeSet",
      "cloudformation:ExecuteChangeSet",
      "cloudformation:DeleteChangeSet",
      "cloudformation:DescribeStacks",
      "cloudformation:DescribeStackEvents",
      "cloudformation:DescribeStackResource",
      "cloudformation:GetTemplate",
    ]
    resources = [local.stack_arns[each.key]]
  }

  # template.yaml uses the Serverless and AWS::Include transforms
  statement {
    sid     = "SamTransforms"
    actions = ["cloudformation:CreateChangeSet"]
    resources = [
      "arn:aws:cloudformation:${local.region}:aws:transform/Serverless-2016-10-31",
      "arn:aws:cloudformation:${local.region}:aws:transform/Include",
    ]
  }

  statement {
    sid = "SamTemplate"
    actions = [
      "cloudformation:GetTemplateSummary",
      "cloudformation:ValidateTemplate",
    ]
    resources = ["*"]
  }

  # The artifact bucket is shared, so only this stack's prefix
  statement {
    sid = "SamArtifacts"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["arn:aws:s3:::${var.sam_artifact_bucket}/${each.value.stack_name}/*"]
  }

  statement {
    sid = "SamArtifactsBucket"
    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket",
    ]
    resources = ["arn:aws:s3:::${var.sam_artifact_bucket}"]
  }

  statement {
    sid       = "FetchTorguapiLayer"
    actions   = ["lambda:GetLayerVersion"]
    resources = [local.layer_arn]
  }

  # After a deploy that changed the stack, clear /nj/officer_diversity/* in the
  # distribution in front of this environment (defined in torgu-api-cloudfront)
  statement {
    sid       = "InvalidateCache"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = ["arn:aws:cloudfront::${local.account}:distribution/${each.value.distribution_id}"]
  }
}

resource "aws_iam_role" "deploy" {
  for_each = var.envs

  name               = "${var.project}-gha-deploy-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.deploy_trust[each.key].json
}

resource "aws_iam_role_policy" "deploy" {
  for_each = var.envs

  name   = "deploy"
  role   = aws_iam_role.deploy[each.key].id
  policy = data.aws_iam_policy_document.deploy[each.key].json
}
