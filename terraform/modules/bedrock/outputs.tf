output "knowledge_base_id" {
  value = awscc_bedrock_knowledge_base.main.knowledge_base_id
}

output "data_source_id" {
  value = awscc_bedrock_data_source.main.data_source_id
}

output "role_arn" {
  value = aws_iam_role.bedrock_kb.arn
}
