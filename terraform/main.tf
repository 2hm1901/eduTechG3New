data "aws_caller_identity" "current" {}

locals {
  account_id        = data.aws_caller_identity.current.account_id
  bedrock_model_arn = length(regexall("^(global|apac|us|eu|au)\\.", var.bedrock_model_id)) > 0 ? "arn:aws:bedrock:${var.region}:${local.account_id}:inference-profile/${var.bedrock_model_id}" : "arn:aws:bedrock:${var.region}::foundation-model/${var.bedrock_model_id}"
}

module "kms" {
  source      = "./modules/kms"
  account_id  = local.account_id
  environment = var.env
}

module "networking" {
  source = "./modules/networking"
  region = var.region
}

module "s3" {
  source      = "./modules/s3"
  account_id  = local.account_id
  kms_key_arn = module.kms.pdf_kms_key_arn
}


module "cognito" {
  source = "./modules/cognito"
}

module "dynamodb" {
  source = "./modules/dynamodb"
}

module "lambda" {
  source                   = "./modules/lambda"
  region                   = var.region
  subnet_id                = module.networking.private_subnet_id
  lambda_security_group_id = module.networking.lambda_security_group_id
  pdf_bucket_name          = module.s3.pdf_bucket_name
  pdf_bucket_arn           = module.s3.pdf_bucket_arn
  source_bucket_name       = module.s3.source_bucket_name
  source_bucket_arn        = module.s3.source_bucket_arn
  kms_key_arn              = module.kms.pdf_kms_key_arn
  bedrock_kb_id            = var.bedrock_kb_id
  bedrock_datasource_id    = var.bedrock_datasource_id
  bedrock_model_arn        = var.bedrock_model_arn != "" ? var.bedrock_model_arn : local.bedrock_model_arn
  bedrock_model_id         = var.bedrock_model_id
  dynamodb_table_name      = module.dynamodb.table_name
  upload_handler_zip       = var.upload_handler_zip
  text_extraction_zip      = var.text_extraction_zip
  chat_zip                 = var.chat_zip
  summarize_quiz_zip       = var.summarize_quiz_zip
  dashboard_zip            = var.dashboard_zip
  api_backend_zip          = var.api_backend_zip
  pypdf_layer_arn          = var.pypdf_layer_arn
  cors_origin              = var.cors_origin
}

module "api_gateway" {
  source             = "./modules/api_gateway"
  user_pool_arn      = module.cognito.user_pool_arn
  upload_handler_arn = module.lambda.upload_handler_arn
  chat_arn           = module.lambda.chat_arn
  summarize_quiz_arn = module.lambda.summarize_quiz_arn
  dashboard_arn      = module.lambda.dashboard_arn
  api_backend_arn    = module.lambda.api_backend_arn
  stage_name         = var.env
  cors_origin        = var.cors_origin
}

module "cloudfront" {
  source                 = "./modules/cloudfront"
  frontend_bucket_domain = module.s3.frontend_bucket_regional_domain
}

module "monitoring" {
  source              = "./modules/monitoring"
  lambda_names        = module.lambda.lambda_names
  lambda_timeouts     = module.lambda.lambda_timeouts
  dynamodb_table_name = module.dynamodb.table_name
}

resource "aws_lambda_permission" "s3_invoke_text_extraction" {
  statement_id  = "AllowS3InvokeTextExtraction"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.text_extraction_name
  principal     = "s3.amazonaws.com"
  source_arn    = module.s3.pdf_bucket_arn
}

resource "aws_s3_bucket_notification" "pdf" {
  bucket = module.s3.pdf_bucket_name

  lambda_function {
    lambda_function_arn = module.lambda.text_extraction_arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [aws_lambda_permission.s3_invoke_text_extraction]
}

resource "aws_s3_bucket_cors_configuration" "pdf" {
  bucket = module.s3.pdf_bucket_name

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "POST", "GET"]
    allowed_origins = [var.pdf_cors_allowed_origin]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket_policy" "pdf" {
  bucket = module.s3.pdf_bucket_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyNonHTTPS"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = ["${module.s3.pdf_bucket_arn}", "${module.s3.pdf_bucket_arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "AllowUploadHandler"
        Effect    = "Allow"
        Principal = { AWS = module.lambda.upload_handler_role_arn }
        Action    = ["s3:PutObject"]
        Resource  = "${module.s3.pdf_bucket_arn}/*"
      },
      {
        Sid       = "AllowApiBackend"
        Effect    = "Allow"
        Principal = { AWS = module.lambda.api_backend_role_arn }
        Action    = ["s3:GetObject", "s3:PutObject"]
        Resource  = "${module.s3.pdf_bucket_arn}/*"
      },
      {
        Sid       = "AllowTextExtraction"
        Effect    = "Allow"
        Principal = { AWS = module.lambda.text_extraction_role_arn }
        Action    = "s3:GetObject"
        Resource  = "${module.s3.pdf_bucket_arn}/*"
      }
    ]
  })
}

resource "aws_s3_bucket_policy" "source" {
  bucket = module.s3.source_bucket_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyNonHTTPS"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = ["${module.s3.source_bucket_arn}", "${module.s3.source_bucket_arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "AllowTextExtraction"
        Effect    = "Allow"
        Principal = { AWS = module.lambda.text_extraction_role_arn }
        Action    = ["s3:PutObject"]
        Resource  = "${module.s3.source_bucket_arn}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "bedrock_kb_source_kms" {
  name = "ai-study-buddy-source-kms-access"
  role = var.bedrock_kb_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = module.kms.pdf_kms_key_arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = "${module.s3.source_bucket_arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = module.s3.source_bucket_arn
      }
    ]
  })
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = module.s3.frontend_bucket_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCloudFrontOAC"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${module.s3.frontend_bucket_arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = module.cloudfront.distribution_arn
          }
        }
      }
    ]
  })
}

resource "aws_lambda_permission" "apigw" {
  for_each = {
    upload_handler = module.lambda.upload_handler_arn
    chat           = module.lambda.chat_arn
    summarize_quiz = module.lambda.summarize_quiz_arn
    dashboard      = module.lambda.dashboard_arn
    api_backend    = module.lambda.api_backend_arn
  }

  statement_id  = "AllowApiGatewayInvoke-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = each.value
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${module.api_gateway.execution_arn}/*/*"
}
