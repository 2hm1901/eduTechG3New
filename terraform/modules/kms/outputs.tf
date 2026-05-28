output "pdf_kms_key_arn" {
  value = aws_kms_key.pdf.arn
}

output "pdf_kms_key_id" {
  value = aws_kms_key.pdf.key_id
}

output "pdf_kms_alias" {
  value = aws_kms_alias.pdf.name
}
