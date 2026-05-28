resource "aws_dynamodb_table" "main" {
  name         = "ai-study-buddy-main-v2"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "sk"

  attribute {
    name = "user_id"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = { Name = "ai-study-buddy-main" }
}
