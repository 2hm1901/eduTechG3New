output "domain_name" {
  value = aws_cloudfront_distribution.main.domain_name
}

output "distribution_arn" {
  value = aws_cloudfront_distribution.main.arn
}

output "oac_id" {
  value = aws_cloudfront_origin_access_control.main.id
}
