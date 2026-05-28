resource "aws_kms_key" "pdf" {
  description             = "KMS key for AI Study Buddy PDF bucket"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  key_usage               = "ENCRYPT_DECRYPT"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AllowAccountRoot"
        Effect   = "Allow"
        Principal = { AWS = "arn:aws:iam::${var.account_id}:root" }
        Action   = "kms:*"
        Resource = "*"
      }
    ]
  })
}

resource "aws_kms_alias" "pdf" {
  name          = "alias/ai-study-buddy-pdf"
  target_key_id = aws_kms_key.pdf.key_id
}
