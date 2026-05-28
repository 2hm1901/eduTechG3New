data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

locals {
  runtime       = "python3.12"
  architectures = ["arm64"]
}

resource "aws_iam_role" "upload_handler" {
  name               = "upload-handler-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy" "upload_handler" {
  name = "upload-handler-policy"
  role = aws_iam_role.upload_handler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${var.pdf_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["kms:GenerateDataKey", "kms:Encrypt", "kms:Decrypt"]
        Resource = var.kms_key_arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.region}:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "text_extraction" {
  name               = "text-extraction-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy" "text_extraction" {
  name = "text-extraction-policy"
  role = aws_iam_role.text_extraction.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${var.pdf_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.pdf_bucket_arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${var.source_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:StartIngestionJob", "bedrock:GetIngestionJob"]
        Resource = "arn:aws:bedrock:${var.region}:*:knowledge-base/*"
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:GenerateDataKey", "kms:Encrypt"]
        Resource = var.kms_key_arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.region}:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "chat" {
  name               = "chat-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy" "chat" {
  name = "chat-policy"
  role = aws_iam_role.chat.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["bedrock:RetrieveAndGenerate", "bedrock:Retrieve"]
        Resource = "arn:aws:bedrock:${var.region}:*:knowledge-base/*"
      },
      {
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:::foundation-model/*",
          "arn:aws:bedrock:${var.region}::foundation-model/*",
          "arn:aws:bedrock:${var.region}:*:inference-profile/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query"]
        Resource = "arn:aws:dynamodb:${var.region}:*:table/${var.dynamodb_table_name}"
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.region}:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "summarize_quiz" {
  name               = "summarize-quiz-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy" "summarize_quiz" {
  name = "summarize-quiz-policy"
  role = aws_iam_role.summarize_quiz.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:::foundation-model/*",
          "arn:aws:bedrock:${var.region}::foundation-model/*",
          "arn:aws:bedrock:${var.region}:*:inference-profile/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${var.source_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.source_bucket_arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem"]
        Resource = "arn:aws:dynamodb:${var.region}:*:table/${var.dynamodb_table_name}"
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.region}:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "dashboard" {
  name               = "dashboard-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy" "dashboard" {
  name = "dashboard-policy"
  role = aws_iam_role.dashboard.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:Query"]
        Resource = "arn:aws:dynamodb:${var.region}:*:table/${var.dynamodb_table_name}"
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.region}:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "api_backend" {
  name               = "api-backend-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy" "api_backend" {
  name = "api-backend-policy"
  role = aws_iam_role.api_backend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
        Resource = "${var.pdf_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["kms:GenerateDataKey", "kms:Encrypt", "kms:Decrypt"]
        Resource = var.kms_key_arn
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem"
        ]
        Resource = "arn:aws:dynamodb:${var.region}:*:table/${var.dynamodb_table_name}"
      },
      {
        Effect = "Allow"
        Action = ["bedrock:Retrieve", "bedrock:RetrieveAndGenerate", "bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:${var.region}:*:knowledge-base/*",
          "arn:aws:bedrock:::foundation-model/*",
          "arn:aws:bedrock:${var.region}::foundation-model/*",
          "arn:aws:bedrock:${var.region}:*:inference-profile/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.region}:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_lambda_function" "upload_handler" {
  function_name    = "ai-study-buddy-upload-handler"
  handler          = "upload_handler.lambda_handler"
  runtime          = local.runtime
  architectures    = local.architectures
  role             = aws_iam_role.upload_handler.arn
  filename         = var.upload_handler_zip
  source_code_hash = filebase64sha256(var.upload_handler_zip)
  timeout          = 60
  memory_size      = 512

  vpc_config {
    subnet_ids         = [var.subnet_id]
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      PDF_BUCKET_NAME = var.pdf_bucket_name
      REGION          = var.region
    }
  }
}

resource "aws_lambda_function" "text_extraction" {
  function_name    = "ai-study-buddy-text-extraction"
  handler          = "text_extraction.lambda_handler"
  runtime          = local.runtime
  architectures    = local.architectures
  role             = aws_iam_role.text_extraction.arn
  filename         = var.text_extraction_zip
  source_code_hash = filebase64sha256(var.text_extraction_zip)
  timeout          = 300
  memory_size      = 1024
  layers           = var.pypdf_layer_arn == null ? [] : [var.pypdf_layer_arn]

  vpc_config {
    subnet_ids         = [var.subnet_id]
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      BEDROCK_KB_ID         = var.bedrock_kb_id
      BEDROCK_DATASOURCE_ID = var.bedrock_datasource_id
      SOURCE_BUCKET_NAME    = var.source_bucket_name
      REGION                = var.region
    }
  }
}

resource "aws_lambda_function" "chat" {
  function_name    = "ai-study-buddy-chat"
  handler          = "chat.lambda_handler"
  runtime          = local.runtime
  architectures    = local.architectures
  role             = aws_iam_role.chat.arn
  filename         = var.chat_zip
  source_code_hash = filebase64sha256(var.chat_zip)
  timeout          = 30
  memory_size      = 512

  vpc_config {
    subnet_ids         = [var.subnet_id]
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      BEDROCK_KB_ID     = var.bedrock_kb_id
      BEDROCK_MODEL_ARN = var.bedrock_model_arn
      DYNAMODB_TABLE    = var.dynamodb_table_name
      REGION            = var.region
    }
  }
}

resource "aws_lambda_function" "summarize_quiz" {
  function_name    = "ai-study-buddy-summarize-quiz"
  handler          = "summarize_quiz.lambda_handler"
  runtime          = local.runtime
  architectures    = local.architectures
  role             = aws_iam_role.summarize_quiz.arn
  filename         = var.summarize_quiz_zip
  source_code_hash = filebase64sha256(var.summarize_quiz_zip)
  timeout          = 60
  memory_size      = 512

  vpc_config {
    subnet_ids         = [var.subnet_id]
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      BEDROCK_MODEL_ID   = var.bedrock_model_id
      DYNAMODB_TABLE     = var.dynamodb_table_name
      REGION             = var.region
      SOURCE_BUCKET_NAME = var.source_bucket_name
    }
  }
}

resource "aws_lambda_function" "dashboard" {
  function_name    = "ai-study-buddy-dashboard"
  handler          = "dashboard.lambda_handler"
  runtime          = local.runtime
  architectures    = local.architectures
  role             = aws_iam_role.dashboard.arn
  filename         = var.dashboard_zip
  source_code_hash = filebase64sha256(var.dashboard_zip)
  timeout          = 15
  memory_size      = 256

  vpc_config {
    subnet_ids         = [var.subnet_id]
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      DYNAMODB_TABLE = var.dynamodb_table_name
      REGION         = var.region
    }
  }
}

resource "aws_lambda_function" "api_backend" {
  function_name    = "ai-study-buddy-api-backend"
  handler          = "src.app.handler"
  runtime          = local.runtime
  architectures    = local.architectures
  role             = aws_iam_role.api_backend.arn
  filename         = var.api_backend_zip
  source_code_hash = filebase64sha256(var.api_backend_zip)
  timeout          = 30
  memory_size      = 512

  vpc_config {
    subnet_ids         = [var.subnet_id]
    security_group_ids = [var.lambda_security_group_id]
  }

  environment {
    variables = {
      AI_BACKEND                    = "bedrock"
      AI_MODEL_ID                   = var.bedrock_model_id
      APP_REGION                    = var.region
      STORAGE_BACKEND               = "s3"
      STORAGE_BUCKET                = var.pdf_bucket_name
      USERSTORE_BACKEND             = "dynamodb"
      USERSTORE_TABLE               = var.dynamodb_table_name
      VECTOR_BACKEND                = "bedrock_kb"
      SERVE_FRONTEND                = "false"
      CORS_ORIGINS                  = var.cors_origin
      VECTOR_BEDROCK_KB_ID          = var.bedrock_kb_id
      VECTOR_BEDROCK_DATA_SOURCE_ID = var.bedrock_datasource_id
    }
  }
}
