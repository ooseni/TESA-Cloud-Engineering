output "site_url" {
  description = "The site's HTTPS address."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "distribution_id" {
  description = "CloudFront distribution ID, for cache invalidations."
  value       = aws_cloudfront_distribution.site.id
}

output "bucket_name" {
  description = "The private bucket that holds the site."
  value       = aws_s3_bucket.site.id
}

output "bucket_regional_domain_name" {
  description = "The bucket's own endpoint, which must refuse direct requests."
  value       = aws_s3_bucket.site.bucket_regional_domain_name
}
