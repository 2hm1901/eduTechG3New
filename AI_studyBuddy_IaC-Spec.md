# AI Study Buddy — IaC Specification (Terraform)

> **Region:** `ap-southeast-2` (Sydney)  
> **Version:** 1.0 | Hackathon Project

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Networking](#2-networking)
3. [Amazon S3](#3-amazon-s3)
4. [Amazon Cognito](#4-amazon-cognito)
5. [Amazon API Gateway](#5-amazon-api-gateway)
6. [AWS Lambda Functions](#6-aws-lambda-functions)
7. [Amazon DynamoDB](#7-amazon-dynamodb)
8. [IAM Roles & Policies](#8-iam-roles--policies-least-privilege)
9. [AWS KMS](#9-aws-kms)
10. [Amazon Bedrock](#10-amazon-bedrock)
11. [Amazon CloudFront](#11-amazon-cloudfront)
12. [Monitoring & Logging](#12-monitoring--logging)
13. [Terraform Structure](#13-terraform-structure)
14. [Deploy Checklist](#14-deploy-checklist)

---

## 1. Architecture Overview

### Workflows

| Workflow | Trigger | Lambda | Services |
|---|---|---|---|
| Upload & Ingest | POST /upload-pdf | Upload Handler | S3 PDF, KMS |
| Text Extraction | S3 Event (ObjectCreated) | Text Extraction | Bedrock KB, Titan Embeddings, S3 Vectors |
| Chat RAG | POST /chat | Chat | Bedrock KB, Claude Haiku 3.5, DynamoDB |
| Summarize / Quiz | POST /summarize, POST /quiz | Summarize Quiz | Claude Haiku 3.5, DynamoDB |
| Dashboard | GET /dashboard | Dashboard | DynamoDB |

### Services Summary

| Category | Service | Resource Name |
|---|---|---|
| Frontend | CloudFront + S3 FE | `ai-study-buddy-frontend-{account_id}` |
| Auth | Amazon Cognito | `ai-study-buddy-user-pool` |
| API Layer | API Gateway REST + JWT Authorizer | `ai-study-buddy-api` |
| Compute | 5 x AWS Lambda (Private Subnet) | See Section 6 |
| Networking | VPC, Private Subnet, IGW, Endpoints, SGs | `ai-study-buddy-vpc` |
| Storage | S3 PDF (KMS), S3 FE, S3 Vector DB | See Section 3 |
| AI Services | Bedrock KB, Claude Haiku 3.5, Titan Embeddings v2 | `ai-study-buddy-kb` |
| Database | DynamoDB (Single Table) | `ai-study-buddy-main` |
| Security | KMS, IAM Roles per Lambda | `alias/ai-study-buddy-pdf` |

---

## 2. Networking

### 2.1 VPC

```hcl
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true   # required for Interface Endpoints
  enable_dns_hostnames = true   # required for Interface Endpoints
  tags = { Name = "ai-study-buddy-vpc" }
}
```

### 2.2 Private Subnet

```hcl
resource "aws_subnet" "private" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "ap-southeast-2a"
  map_public_ip_on_launch = false
  tags = { Name = "ai-study-buddy-private-subnet" }
}
```

### 2.3 Internet Gateway

```hcl
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "ai-study-buddy-igw" }
}
```

### 2.4 Gateway Endpoints (free — no cost)

| Endpoint | service_name | Purpose |
|---|---|---|
| S3 Gateway | `com.amazonaws.ap-southeast-2.s3` | S3 traffic stays in AWS network |
| DynamoDB Gateway | `com.amazonaws.ap-southeast-2.dynamodb` | DynamoDB traffic stays in AWS network |

```hcl
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.ap-southeast-2.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.ap-southeast-2.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
}
```

### 2.5 Interface Endpoints (Bedrock — billed per hour)

> Lambda trong Private Subnet bắt buộc phải có các endpoints này để gọi Bedrock.

| Endpoint Name | service_name |
|---|---|
| Bedrock | `com.amazonaws.ap-southeast-2.bedrock` |
| Bedrock Runtime | `com.amazonaws.ap-southeast-2.bedrock-runtime` |
| Bedrock Agent | `com.amazonaws.ap-southeast-2.bedrock-agent` |
| Bedrock Agent Runtime | `com.amazonaws.ap-southeast-2.bedrock-agent-runtime` |

```hcl
locals {
  bedrock_endpoints = [
    "bedrock",
    "bedrock-runtime",
    "bedrock-agent",
    "bedrock-agent-runtime",
  ]
}

resource "aws_vpc_endpoint" "bedrock" {
  for_each = toset(local.bedrock_endpoints)

  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.ap-southeast-2.${each.key}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true  # required
  subnet_ids          = [aws_subnet.private.id]
  security_group_ids  = [aws_security_group.endpoints.id]
}
```

### 2.6 Security Groups

#### Lambda Security Group

```hcl
resource "aws_security_group" "lambda" {
  name   = "ai-study-buddy-lambda-sg"
  vpc_id = aws_vpc.main.id

  # No inbound rules — Lambda triggered by API Gateway / S3 event
  egress {
    description     = "HTTPS to Interface Endpoints"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.endpoints.id]
  }
  egress {
    description = "HTTPS to S3/DynamoDB Gateway Endpoints"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    prefix_list_ids = [
      aws_vpc_endpoint.s3.prefix_list_id,
      aws_vpc_endpoint.dynamodb.prefix_list_id,
    ]
  }
}
```

#### Endpoints Security Group

```hcl
resource "aws_security_group" "endpoints" {
  name   = "ai-study-buddy-endpoints-sg"
  vpc_id = aws_vpc.main.id

  ingress {
    description     = "HTTPS from Lambda"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }
}
```

---

## 3. Amazon S3

### 3.1 S3 Frontend Bucket (S3 FE)

```hcl
# Bucket
resource "aws_s3_bucket" "frontend" {
  bucket = "ai-study-buddy-frontend-${var.account_id}"
}

# Static website hosting
resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  index_document { suffix = "index.html" }
  error_document { key    = "error.html" }
}

# Allow CloudFront OAC (block public direct access)
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = false  # CloudFront OAC policy needed
  ignore_public_acls      = true
  restrict_public_buckets = false
}
```

### 3.2 S3 PDF Bucket

```hcl
resource "aws_s3_bucket" "pdf" {
  bucket = "ai-study-buddy-pdf-${var.account_id}"
}

# Encryption with KMS
resource "aws_s3_bucket_server_side_encryption_configuration" "pdf" {
  bucket = aws_s3_bucket.pdf.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.pdf.arn
    }
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "pdf" {
  bucket                  = aws_s3_bucket.pdf.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Versioning
resource "aws_s3_bucket_versioning" "pdf" {
  bucket = aws_s3_bucket.pdf.id
  versioning_configuration { status = "Enabled" }
}

# CORS — allow presigned URL upload from CloudFront domain
resource "aws_s3_bucket_cors_configuration" "pdf" {
  bucket = aws_s3_bucket.pdf.id
  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "POST", "GET"]
    allowed_origins = ["https://${aws_cloudfront_distribution.main.domain_name}"]
    max_age_seconds = 3000
  }
}

# S3 Event Trigger → Lambda Text Extraction
resource "aws_s3_bucket_notification" "pdf" {
  bucket = aws_s3_bucket.pdf.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.text_extraction.arn
    events              = ["s3:ObjectCreated:*"]
  }
  depends_on = [aws_lambda_permission.s3_invoke_text_extraction]
}

# Bucket Policy — deny HTTP, allow Lambda roles only
resource "aws_s3_bucket_policy" "pdf" {
  bucket = aws_s3_bucket.pdf.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyNonHTTPS"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = ["${aws_s3_bucket.pdf.arn}", "${aws_s3_bucket.pdf.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid    = "AllowUploadHandler"
        Effect = "Allow"
        Principal = { AWS = aws_iam_role.upload_handler.arn }
        Action   = ["s3:PutObject", "s3:GeneratePresignedUrl"]
        Resource = "${aws_s3_bucket.pdf.arn}/*"
      },
      {
        Sid    = "AllowTextExtraction"
        Effect = "Allow"
        Principal = { AWS = aws_iam_role.text_extraction.arn }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.pdf.arn}/*"
      }
    ]
  })
}
```

### 3.3 S3 Vector DB Bucket

```hcl
resource "aws_s3_bucket" "vectors" {
  bucket = "ai-study-buddy-vectors-${var.account_id}"
}

resource "aws_s3_bucket_public_access_block" "vectors" {
  bucket                  = aws_s3_bucket.vectors.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

> **Note:** Vector index được tạo và quản lý bởi Bedrock KB. Không cần config thêm trên bucket này.

---

## 4. Amazon Cognito

### 4.1 User Pool

```hcl
resource "aws_cognito_user_pool" "main" {
  name = "ai-study-buddy-user-pool"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }

  mfa_configuration = "OFF"

  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }
}
```

### 4.2 User Pool Client

```hcl
resource "aws_cognito_user_pool_client" "main" {
  name         = "ai-study-buddy-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false  # SPA frontend

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  token_validity_units {
    access_token  = "hours"
    refresh_token = "days"
  }
  access_token_validity  = 1
  refresh_token_validity = 30
}
```

---

## 5. Amazon API Gateway

### 5.1 REST API

```hcl
resource "aws_api_gateway_rest_api" "main" {
  name = "ai-study-buddy-api"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}
```

### 5.2 Cognito JWT Authorizer

```hcl
resource "aws_api_gateway_authorizer" "cognito" {
  name            = "cognito-jwt-authorizer"
  rest_api_id     = aws_api_gateway_rest_api.main.id
  type            = "COGNITO_USER_POOLS"
  provider_arns   = [aws_cognito_user_pool.main.arn]
  identity_source = "method.request.header.Authorization"
}
```

### 5.3 Routes & Lambda Integration

| Route | Method | Lambda | Auth Required |
|---|---|---|---|
| `/upload-pdf` | POST | Lambda Upload Handler | Cognito JWT |
| `/chat` | POST | Lambda Chat | Cognito JWT |
| `/summarize` | POST | Lambda Summarize Quiz | Cognito JWT |
| `/quiz` | POST | Lambda Summarize Quiz | Cognito JWT |
| `/dashboard` | GET | Lambda Dashboard | Cognito JWT |

> Mỗi route cần: `aws_api_gateway_resource` + `aws_api_gateway_method` (authorization = `COGNITO_USER_POOLS`) + `aws_api_gateway_integration` (type = `AWS_PROXY`)

---

## 6. AWS Lambda Functions

### Common Config (applies to all Lambda)

```hcl
runtime       = "python3.12"
architectures = ["arm64"]   # cheaper than x86_64
vpc_config {
  subnet_ids         = [aws_subnet.private.id]
  security_group_ids = [aws_security_group.lambda.id]
}
```

### 6.1 Upload Handler

| Parameter | Value |
|---|---|
| `function_name` | `ai-study-buddy-upload-handler` |
| `handler` | `upload_handler.lambda_handler` |
| `timeout` | `60` |
| `memory_size` | `512` |
| `trigger` | API Gateway POST /upload-pdf |
| `iam_role` | `upload-handler-role` (Section 8.1) |

```hcl
environment {
  variables = {
    PDF_BUCKET_NAME = aws_s3_bucket.pdf.bucket
    REGION          = "ap-southeast-2"
  }
}
```

**Logic:** Nhận metadata từ client → generate S3 presigned URL → trả URL về cho client upload trực tiếp lên S3.

---

### 6.2 Text Extraction

| Parameter | Value |
|---|---|
| `function_name` | `ai-study-buddy-text-extraction` |
| `handler` | `text_extraction.lambda_handler` |
| `timeout` | `300` |
| `memory_size` | `1024` |
| `trigger` | S3 Event `s3:ObjectCreated:*` từ PDF bucket |
| `iam_role` | `text-extraction-role` (Section 8.2) |
| `layers` | pypdf Lambda Layer |

```hcl
environment {
  variables = {
    BEDROCK_KB_ID         = aws_bedrockagent_knowledge_base.main.id
    BEDROCK_DATASOURCE_ID = aws_bedrockagent_data_source.main.data_source_id
    REGION                = "ap-southeast-2"
  }
}
```

**Logic:** Lấy PDF từ S3 → extract text bằng pypdf → gọi `bedrock-agent:StartIngestionJob` → Bedrock KB tự chunking + embedding + lưu vào S3 Vector DB.

```python
# Pseudocode
import boto3

bedrock_agent = boto3.client('bedrock-agent', region_name='ap-southeast-2')

bedrock_agent.start_ingestion_job(
    knowledgeBaseId=os.environ['BEDROCK_KB_ID'],
    dataSourceId=os.environ['BEDROCK_DATASOURCE_ID'],
)
```

---

### 6.3 Chat

| Parameter | Value |
|---|---|
| `function_name` | `ai-study-buddy-chat` |
| `handler` | `chat.lambda_handler` |
| `timeout` | `30` |
| `memory_size` | `512` |
| `trigger` | API Gateway POST /chat |
| `iam_role` | `chat-role` (Section 8.3) |

```hcl
environment {
  variables = {
    BEDROCK_KB_ID      = aws_bedrockagent_knowledge_base.main.id
    BEDROCK_MODEL_ARN  = "arn:aws:bedrock:ap-southeast-2::foundation-model/anthropic.claude-3-5-haiku-20241022-v1:0"
    DYNAMODB_TABLE     = aws_dynamodb_table.main.name
    REGION             = "ap-southeast-2"
  }
}
```

**Logic:** Gọi `bedrock-agent-runtime:RetrieveAndGenerate` → lưu câu hỏi + câu trả lời vào DynamoDB với sk = `CHAT#<timestamp>`.

```python
# Pseudocode
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='ap-southeast-2')

response = bedrock_agent_runtime.retrieve_and_generate(
    input={'text': user_question},
    retrieveAndGenerateConfiguration={
        'type': 'KNOWLEDGE_BASE',
        'knowledgeBaseConfiguration': {
            'knowledgeBaseId': os.environ['BEDROCK_KB_ID'],
            'modelArn': os.environ['BEDROCK_MODEL_ARN'],
        }
    }
)
```

---

### 6.4 Summarize / Quiz

| Parameter | Value |
|---|---|
| `function_name` | `ai-study-buddy-summarize-quiz` |
| `handler` | `summarize_quiz.lambda_handler` |
| `timeout` | `60` |
| `memory_size` | `512` |
| `trigger` | API Gateway POST /summarize và POST /quiz |
| `iam_role` | `summarize-quiz-role` (Section 8.4) |

```hcl
environment {
  variables = {
    BEDROCK_MODEL_ID = "anthropic.claude-3-5-haiku-20241022-v1:0"
    DYNAMODB_TABLE   = aws_dynamodb_table.main.name
    REGION           = "ap-southeast-2"
  }
}
```

**Logic:** Gọi `bedrock-runtime:InvokeModel` với Claude Haiku 3.5 → lưu kết quả vào DynamoDB với sk = `SUMMARY#<docId>` hoặc `QUIZ#<docId>#<timestamp>`.

---

### 6.5 Dashboard

| Parameter | Value |
|---|---|
| `function_name` | `ai-study-buddy-dashboard` |
| `handler` | `dashboard.lambda_handler` |
| `timeout` | `15` |
| `memory_size` | `256` |
| `trigger` | API Gateway GET /dashboard |
| `iam_role` | `dashboard-role` (Section 8.5) |

```hcl
environment {
  variables = {
    DYNAMODB_TABLE = aws_dynamodb_table.main.name
    REGION         = "ap-southeast-2"
  }
}
```

**Logic:** Query DynamoDB theo `userId` → trả về User state, Chat history, Quizzes, Summaries, Learning progress.

---

## 7. Amazon DynamoDB

### 7.1 Table Config

```hcl
resource "aws_dynamodb_table" "main" {
  name         = "ai-study-buddy-main"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"
  range_key    = "sk"

  attribute {
    name = "userId"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  server_side_encryption {
    enabled = true  # AWS managed key
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = { Name = "ai-study-buddy-main" }
}
```

### 7.2 Single Table Data Model

| userId (PK) | sk (SK) | Data Type | Key Attributes |
|---|---|---|---|
| `user#<id>` | `PROFILE` | User state | `email`, `name`, `createdAt` |
| `user#<id>` | `CHAT#<timestamp>` | Chat history | `question`, `answer`, `documentId` |
| `user#<id>` | `QUIZ#<docId>#<ts>` | Quizzes | `questions[]`, `score`, `completedAt` |
| `user#<id>` | `SUMMARY#<docId>` | Summaries | `summary`, `documentName`, `createdAt` |
| `user#<id>` | `PROGRESS` | Learning progress | `totalDocs`, `totalChats`, `lastActive` |

---

## 8. IAM Roles & Policies (Least Privilege)

> Mỗi Lambda có IAM Role riêng. Không dùng chung role.

### 8.1 Upload Handler Role

```json
{
  "Effect": "Allow",
  "Action": [
    "s3:PutObject",
    "s3:GeneratePresignedUrl"
  ],
  "Resource": "arn:aws:s3:::ai-study-buddy-pdf-*/*"
},
{
  "Effect": "Allow",
  "Action": [
    "logs:CreateLogGroup",
    "logs:CreateLogStream",
    "logs:PutLogEvents"
  ],
  "Resource": "arn:aws:logs:ap-southeast-2:*:*"
},
{
  "Effect": "Allow",
  "Action": [
    "ec2:CreateNetworkInterface",
    "ec2:DescribeNetworkInterfaces",
    "ec2:DeleteNetworkInterface"
  ],
  "Resource": "*"
}
```

### 8.2 Text Extraction Role

```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject"],
  "Resource": "arn:aws:s3:::ai-study-buddy-pdf-*/*"
},
{
  "Effect": "Allow",
  "Action": [
    "bedrock:StartIngestionJob",
    "bedrock:GetIngestionJob"
  ],
  "Resource": "arn:aws:bedrock:ap-southeast-2:*:knowledge-base/*"
},
{
  "Effect": "Allow",
  "Action": ["kms:Decrypt"],
  "Resource": "<KMS_KEY_ARN>"
},
{
  "Effect": "Allow",
  "Action": ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"],
  "Resource": "*"
}
```

### 8.3 Chat Role

```json
{
  "Effect": "Allow",
  "Action": [
    "bedrock:RetrieveAndGenerate",
    "bedrock:Retrieve"
  ],
  "Resource": "arn:aws:bedrock:ap-southeast-2:*:knowledge-base/*"
},
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "arn:aws:bedrock:ap-southeast-2::foundation-model/anthropic.claude-*"
},
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:PutItem",
    "dynamodb:GetItem",
    "dynamodb:Query"
  ],
  "Resource": "arn:aws:dynamodb:ap-southeast-2:*:table/ai-study-buddy-main"
},
{
  "Effect": "Allow",
  "Action": ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"],
  "Resource": "*"
}
```

### 8.4 Summarize / Quiz Role

```json
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "arn:aws:bedrock:ap-southeast-2::foundation-model/anthropic.claude-*"
},
{
  "Effect": "Allow",
  "Action": ["dynamodb:PutItem", "dynamodb:GetItem"],
  "Resource": "arn:aws:dynamodb:ap-southeast-2:*:table/ai-study-buddy-main"
},
{
  "Effect": "Allow",
  "Action": ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"],
  "Resource": "*"
}
```

### 8.5 Dashboard Role

```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:GetItem", "dynamodb:Query"],
  "Resource": "arn:aws:dynamodb:ap-southeast-2:*:table/ai-study-buddy-main"
},
{
  "Effect": "Allow",
  "Action": ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"],
  "Resource": "*"
}
```

---

## 9. AWS KMS

```hcl
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
      },
      {
        Sid    = "AllowUploadHandlerEncrypt"
        Effect = "Allow"
        Principal = { AWS = aws_iam_role.upload_handler.arn }
        Action   = ["kms:GenerateDataKey", "kms:Encrypt"]
        Resource = "*"
      },
      {
        Sid    = "AllowTextExtractionDecrypt"
        Effect = "Allow"
        Principal = { AWS = aws_iam_role.text_extraction.arn }
        Action   = ["kms:Decrypt"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_kms_alias" "pdf" {
  name          = "alias/ai-study-buddy-pdf"
  target_key_id = aws_kms_key.pdf.key_id
}
```

---

## 10. Amazon Bedrock

> **⚠️ Manual Step Required:** Enable Model Access trong AWS Console → Bedrock → Model access trước khi deploy.

### Models cần enable

| Model | Model ID | Dùng cho |
|---|---|---|
| Claude Haiku 3.5 | `anthropic.claude-3-5-haiku-20241022-v1:0` | Generation (Chat, Summarize, Quiz) |
| Titan Embeddings v2 | `amazon.titan-embed-text-v2:0` | Embedding (Bedrock KB) |

> **Note:** Kiểm tra availability của các models này tại region `ap-southeast-2`. Một số models Anthropic có thể chưa available tại Sydney — nếu vậy dùng `us-east-1` cho Bedrock calls hoặc dùng cross-region inference.

### 10.1 Knowledge Base

```hcl
resource "aws_bedrockagent_knowledge_base" "main" {
  name     = "ai-study-buddy-kb"
  role_arn = aws_iam_role.bedrock_kb.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:ap-southeast-2::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }

  storage_configuration {
    type = "S3_VECTORS"
    s3_vectors_configuration {
      vector_bucket_arn = aws_s3_bucket.vectors.arn
    }
  }
}
```

### 10.2 Data Source (trỏ vào S3 PDF bucket)

```hcl
resource "aws_bedrockagent_data_source" "main" {
  name             = "ai-study-buddy-s3-datasource"
  knowledge_base_id = aws_bedrockagent_knowledge_base.main.id

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn          = aws_s3_bucket.pdf.arn
      inclusion_prefixes  = ["/"]
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 512
        overlap_percentage = 10
      }
    }
  }
}
```

### 10.3 Bedrock KB IAM Role

```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:ListBucket"],
  "Resource": [
    "arn:aws:s3:::ai-study-buddy-pdf-*",
    "arn:aws:s3:::ai-study-buddy-pdf-*/*",
    "arn:aws:s3:::ai-study-buddy-vectors-*",
    "arn:aws:s3:::ai-study-buddy-vectors-*/*"
  ]
},
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "arn:aws:bedrock:ap-southeast-2::foundation-model/amazon.titan-embed-text-v2:0"
}
```

---

## 11. Amazon CloudFront

```hcl
# Origin Access Control
resource "aws_cloudfront_origin_access_control" "main" {
  name                              = "ai-study-buddy-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "main" {
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "S3-Frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.main.id
  }

  enabled             = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"  # US, Canada, Europe (cheapest)

  default_cache_behavior {
    target_origin_id       = "S3-Frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
  }

  # SPA routing — redirect 403/404 to index.html
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }
  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
```

---

## 12. Monitoring & Logging

### 12.1 CloudWatch Log Groups

```hcl
locals {
  lambda_names = [
    "upload-handler",
    "text-extraction",
    "chat",
    "summarize-quiz",
    "dashboard",
  ]
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = toset(local.lambda_names)
  name              = "/aws/lambda/ai-study-buddy-${each.key}"
  retention_in_days = 14
}
```

### 12.2 CloudWatch Alarms

| Alarm | Metric | Threshold |
|---|---|---|
| Lambda Errors | `Errors > 0` | 5 lần trong 5 phút |
| Lambda Throttles | `Throttles > 0` | 3 lần trong 5 phút |
| Lambda Duration | `Duration > timeout * 0.8` | Cảnh báo sắp timeout |
| DynamoDB System Errors | `SystemErrors > 0` | 1 lần |

---

## 13. Terraform Structure

```
terraform/
├── main.tf                 # Root module
├── variables.tf            # Input variables
├── outputs.tf              # Outputs (API URL, CloudFront URL, KB ID...)
├── terraform.tfvars        # Actual values — DO NOT COMMIT
├── versions.tf             # Required providers & versions
└── modules/
    ├── networking/         # VPC, Subnet, IGW, Endpoints, Security Groups
    ├── s3/                 # S3 FE, S3 PDF, S3 Vector DB
    ├── cognito/            # User Pool, Client
    ├── api_gateway/        # REST API, Authorizer, Routes
    ├── lambda/             # 5 Lambda functions + IAM Roles
    ├── dynamodb/           # Main table
    ├── bedrock/            # KB, Data Source, IAM Role
    ├── kms/                # KMS Key + Alias
    ├── cloudfront/         # Distribution + OAC
    └── monitoring/         # CloudWatch Log Groups + Alarms
```

### variables.tf

```hcl
variable "region"     { default = "ap-southeast-2" }
variable "account_id" { description = "AWS Account ID" }
variable "env"        { default = "hackathon" }
```

### versions.tf

```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}
```

### Deploy Order

| Step | Module | Reason |
|---|---|---|
| 1 | `kms` | Required before encrypted S3 |
| 2 | `networking` | VPC/Subnet required before Lambda |
| 3 | `s3` | Required before Bedrock Data Source |
| 4 | `cognito` | Required before API Gateway Authorizer |
| 5 | `dynamodb` | Required before Lambda env vars |
| 6 | `bedrock` | KB ID required before Lambda env vars |
| 7 | `lambda` | Depends on all above |
| 8 | `api_gateway` | Requires Lambda ARNs |
| 9 | `cloudfront` | Deploy last |
| 10 | `monitoring` | After Lambda Log Groups exist |

---

## 14. Deploy Checklist

### Pre-deploy (Manual Steps)

- [ ] Enable Bedrock Model Access trong AWS Console: `anthropic.claude-3-5-haiku-20241022-v1:0`
- [ ] Enable Bedrock Model Access: `amazon.titan-embed-text-v2:0`
- [ ] Confirm model availability tại `ap-southeast-2` — nếu không available, dùng cross-region inference
- [ ] Setup AWS CLI: `aws configure` với region `ap-southeast-2`
- [ ] Tạo `terraform.tfvars` với `account_id`

### Terraform Deploy

```bash
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

### Post-deploy Verification

- [ ] Upload frontend build lên S3 FE bucket
- [ ] Test Cognito signup → login → nhận JWT token
- [ ] Test `POST /upload-pdf` → nhận presigned URL → upload PDF
- [ ] Kiểm tra S3 Event trigger → Lambda Text Extraction logs trong CloudWatch
- [ ] Kiểm tra Bedrock KB Ingestion Job status (Console hoặc CLI)
- [ ] Test `POST /chat` với câu hỏi về nội dung PDF vừa upload
- [ ] Test `POST /summarize`
- [ ] Test `POST /quiz`
- [ ] Test `GET /dashboard` → kiểm tra data từ DynamoDB

### Useful CLI Commands

```bash
# Check Bedrock KB ingestion job status
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id <KB_ID> \
  --data-source-id <DS_ID> \
  --region ap-southeast-2

# Check Lambda logs
aws logs tail /aws/lambda/ai-study-buddy-text-extraction \
  --follow \
  --region ap-southeast-2

# Check available Bedrock models in ap-southeast-2
aws bedrock list-foundation-models \
  --region ap-southeast-2 \
  --query 'modelSummaries[?contains(modelId, `claude`) || contains(modelId, `titan-embed`)].modelId'
```
