output "frontend_bucket_name" {
  value = aws_s3_bucket.frontend.bucket
}

output "frontend_bucket_arn" {
  value = aws_s3_bucket.frontend.arn
}

output "frontend_bucket_regional_domain" {
  value = aws_s3_bucket.frontend.bucket_regional_domain_name
}

output "pdf_bucket_name" {
  value = aws_s3_bucket.pdf.bucket
}

output "pdf_bucket_arn" {
  value = aws_s3_bucket.pdf.arn
}

output "source_bucket_name" {
  value = aws_s3_bucket.source.bucket
}

output "source_bucket_arn" {
  value = aws_s3_bucket.source.arn
}

