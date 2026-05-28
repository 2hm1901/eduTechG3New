output "api_invoke_url" {
  value = module.api_gateway.invoke_url
}

output "cloudfront_domain" {
  value = module.cloudfront.domain_name
}

output "pdf_bucket_name" {
  value = module.s3.pdf_bucket_name
}

output "frontend_bucket_name" {
  value = module.s3.frontend_bucket_name
}


