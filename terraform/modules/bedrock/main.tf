data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "bedrock_kb" {
  name               = "ai-study-buddy-bedrock-kb-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy" "bedrock_kb" {
  name = "ai-study-buddy-bedrock-kb-policy"
  role = aws_iam_role.bedrock_kb.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          var.source_bucket_arn,
          "${var.source_bucket_arn}/*",
          var.s3_vectors_bucket_arn,
          "${var.s3_vectors_bucket_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = var.embedding_model_arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3vectors:QueryVectors",
          "s3vectors:PutVectors",
          "s3vectors:UpdateVectors",
          "s3vectors:DeleteVectors",
          "s3vectors:GetIndex",
          "s3vectors:DescribeIndex"
        ]
        Resource = var.s3_vectors_index_arn
      }
    ]
  })
}

resource "awscc_bedrock_knowledge_base" "main" {
  name     = "ai-study-buddy-kb"
  role_arn = aws_iam_role.bedrock_kb.arn

  knowledge_base_configuration = {
    type = "VECTOR"
    vector_knowledge_base_configuration = {
      embedding_model_arn = var.embedding_model_arn
    }
  }

  storage_configuration = {
    type = "S3_VECTORS"
    s3_vectors_configuration = {
      vector_bucket_arn = var.s3_vectors_bucket_arn
      index_arn         = var.s3_vectors_index_arn
    }
  }
}

resource "awscc_bedrock_data_source" "main" {
  name              = "ai-study-buddy-s3-datasource"
  knowledge_base_id = awscc_bedrock_knowledge_base.main.knowledge_base_id

  data_source_configuration = {
    type = "S3"
    s3_configuration = {
      bucket_arn         = var.source_bucket_arn
      inclusion_prefixes = ["source/"]
    }
  }

  vector_ingestion_configuration = {
    chunking_configuration = {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration = {
        max_tokens         = 512
        overlap_percentage = 10
      }
    }
  }
}
