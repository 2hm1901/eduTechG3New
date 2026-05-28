resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = { Name = "ai-study-buddy-vpc" }
}

resource "aws_subnet" "private" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.region}a"
  map_public_ip_on_launch = false
  tags = { Name = "ai-study-buddy-private-subnet" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "ai-study-buddy-igw" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "ai-study-buddy-private-rt" }
}

resource "aws_route_table_association" "private" {
  route_table_id = aws_route_table.private.id
  subnet_id      = aws_subnet.private.id
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
}

resource "aws_security_group" "lambda" {
  name   = "ai-study-buddy-lambda-sg"
  vpc_id = aws_vpc.main.id

  egress {
    description = "HTTPS to Interface Endpoints"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
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
  service_name        = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [aws_subnet.private.id]
  security_group_ids  = [aws_security_group.endpoints.id]
}
