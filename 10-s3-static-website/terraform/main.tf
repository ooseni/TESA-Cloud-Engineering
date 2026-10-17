# A private S3 bucket served over HTTPS by CloudFront through Origin Access Control (OAC).
# Nothing in the bucket is public: Block Public Access is on, ACLs are disabled, and the bucket policy
# accepts reads from this one distribution only.

locals {
  content_types = {
    html = "text/html; charset=utf-8"
    css  = "text/css; charset=utf-8"
    js   = "text/javascript; charset=utf-8"
    svg  = "image/svg+xml"
    png  = "image/png"
    jpg  = "image/jpeg"
    ico  = "image/x-icon"
    txt  = "text/plain; charset=utf-8"
  }
  site_files = fileset(var.site_dir, "**")
}

# ---------------------------------------------------------------------------- bucket

resource "aws_s3_bucket" "site" {
  #checkov:skip=CKV_AWS_18:Server access logs for a few static pages are not worth a second bucket; CloudFront logging is listed under production changes.
  #checkov:skip=CKV_AWS_144:Cross-Region replication is unnecessary: the site is rebuilt from the repository in minutes.
  #checkov:skip=CKV_AWS_145:SSE-S3 encrypts every object; a KMS key adds cost and key-policy grants for CloudFront with no gain for public pages.
  #checkov:skip=CKV2_AWS_62:No consumer needs event notifications for this bucket.
  bucket_prefix = var.name_prefix

  # The content lives in the repository, so the bucket and every object version can be destroyed safely.
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    object_ownership = "BucketOwnerEnforced" # ACLs off: only policies grant access
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "site" {
  bucket = aws_s3_bucket.site.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.site]
}

# Reads from this distribution only, and nothing over plain HTTP.
data "aws_iam_policy_document" "site" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.site.arn, "${aws_s3_bucket.site.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = data.aws_iam_policy_document.site.json

  # Block Public Access must be in place first, so the policy is never applied to an open bucket.
  depends_on = [aws_s3_bucket_public_access_block.site]
}

resource "aws_s3_object" "site" {
  for_each = local.site_files

  bucket        = aws_s3_bucket.site.id
  key           = each.value
  source        = "${var.site_dir}/${each.value}"
  etag          = filemd5("${var.site_dir}/${each.value}")
  content_type  = lookup(local.content_types, lower(element(split(".", each.value), length(split(".", each.value)) - 1)), "application/octet-stream")
  cache_control = "public, max-age=300"
}

# ---------------------------------------------------------------------------- CloudFront

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_response_headers_policy" "security_headers" {
  name = "Managed-SecurityHeadersPolicy"
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${aws_s3_bucket.site.id}-oac"
  description                       = "CloudFront signs every request to the private bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "site" {
  #checkov:skip=CKV_AWS_68:AWS WAF costs more than this static site; it is listed under production changes.
  #checkov:skip=CKV2_AWS_47:Follows from CKV_AWS_68: no web ACL is attached.
  #checkov:skip=CKV_AWS_86:Standard logging is listed under production changes.
  #checkov:skip=CKV_AWS_174:The default cloudfront.net certificate cannot set a minimum TLS version; a custom domain with an ACM certificate is listed under production changes.
  #checkov:skip=CKV2_AWS_42:Same reason as CKV_AWS_174: no custom domain yet.
  #checkov:skip=CKV_AWS_310:A second origin for failover is unnecessary for a single private bucket.
  #checkov:skip=CKV_AWS_374:The site is public by design, so no geographic restriction applies.
  comment             = "TESA-Cloud-Engineering module 10: private S3 site"
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  default_root_object = "index.html"
  price_class         = var.price_class

  origin {
    origin_id                = "s3-site"
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id           = "s3-site"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    viewer_protocol_policy     = "redirect-to-https"
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security_headers.id
  }

  # Without s3:ListBucket, S3 answers a missing key with 403, so both codes show the error page as a 404.
  dynamic "custom_error_response" {
    for_each = [403, 404]
    content {
      error_code            = custom_error_response.value
      response_code         = 404
      response_page_path    = "/error.html"
      error_caching_min_ttl = 60
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
