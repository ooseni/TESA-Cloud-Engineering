# GitHub Actions signs in with short-lived OIDC tokens instead of stored access keys. Two roles, each
# trusted by one kind of run only:
#   plan  - pull request runs of this repository: read-only, plus the state lock
#   apply - runs on the main branch of this repository: the changes the stack needs, in one Region

locals {
  oidc_host    = "token.actions.githubusercontent.com"
  state_object = "${aws_s3_bucket.state.arn}/${var.state_key}"
  lock_object  = "${aws_s3_bucket.state.arn}/${var.state_key}.tflock"
  al2023_param = "arn:aws:ssm:${var.region}::parameter/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://${local.oidc_host}"
  client_id_list = ["sts.amazonaws.com"]
}

# ---------------------------------------------------------------------------- trust

data "aws_iam_policy_document" "trust" {
  for_each = {
    plan  = "${var.github_subject_prefix}:pull_request"
    apply = "${var.github_subject_prefix}:ref:refs/heads/main"
  }

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    # an exact subject, never a wildcard: another repository, branch or fork cannot match
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = [each.value]
    }
  }
}

# ---------------------------------------------------------------------------- permissions

# What both roles need to plan: read the state, take and release the lock, and read the resources.
data "aws_iam_policy_document" "plan" {
  statement {
    sid       = "ListStatePrefix"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${dirname(var.state_key)}/*"]
    }
  }

  statement {
    sid       = "ReadState"
    actions   = ["s3:GetObject"]
    resources = [local.state_object]
  }

  statement {
    sid       = "StateLock"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [local.lock_object]
  }

  statement {
    #checkov:skip=CKV_AWS_356:EC2 Describe actions do not support resource-level permissions.
    sid       = "ReadEc2"
    actions   = ["ec2:Describe*"]
    resources = ["*"]
  }

  statement {
    sid       = "ReadAmiParameter"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [local.al2023_param]
  }
}

# The apply role adds: write the state, and create, change and delete the stack's network and instance,
# in the stack's Region only. No IAM, no other service.
data "aws_iam_policy_document" "apply" {
  source_policy_documents = [data.aws_iam_policy_document.plan.json]

  statement {
    sid       = "WriteState"
    actions   = ["s3:PutObject"]
    resources = [local.state_object]
  }

  statement {
    #checkov:skip=CKV_AWS_355:Create actions cannot name resources that do not exist yet; the Region condition limits them.
    #checkov:skip=CKV_AWS_290:Same reason: write actions on resources created by this stack.
    sid = "ManageStack"
    actions = [
      "ec2:CreateVpc", "ec2:DeleteVpc", "ec2:ModifyVpcAttribute",
      "ec2:CreateSubnet", "ec2:DeleteSubnet", "ec2:ModifySubnetAttribute",
      "ec2:CreateInternetGateway", "ec2:DeleteInternetGateway",
      "ec2:AttachInternetGateway", "ec2:DetachInternetGateway",
      "ec2:CreateRouteTable", "ec2:DeleteRouteTable", "ec2:CreateRoute", "ec2:DeleteRoute",
      "ec2:AssociateRouteTable", "ec2:DisassociateRouteTable",
      "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup",
      "ec2:AuthorizeSecurityGroupIngress", "ec2:AuthorizeSecurityGroupEgress",
      "ec2:RevokeSecurityGroupIngress", "ec2:RevokeSecurityGroupEgress",
      "ec2:ModifySecurityGroupRules",
      "ec2:RunInstances", "ec2:TerminateInstances",
      "ec2:ModifyInstanceAttribute", "ec2:ModifyInstanceMetadataOptions",
      "ec2:CreateTags", "ec2:DeleteTags",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.region]
    }
  }
}

# ---------------------------------------------------------------------------- roles

resource "aws_iam_role" "ci" {
  for_each = data.aws_iam_policy_document.trust

  name                 = "tesa-m13-${each.key}"
  description          = "GitHub Actions ${each.key} role for ${var.github_repository}"
  assume_role_policy   = each.value.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "plan" {
  name   = "terraform-plan"
  role   = aws_iam_role.ci["plan"].id
  policy = data.aws_iam_policy_document.plan.json
}

resource "aws_iam_role_policy" "apply" {
  name   = "terraform-apply"
  role   = aws_iam_role.ci["apply"].id
  policy = data.aws_iam_policy_document.apply.json
}
