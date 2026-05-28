output "rest_api_id" {
  value = aws_api_gateway_rest_api.main.id
}

output "execution_arn" {
  value = aws_api_gateway_rest_api.main.execution_arn
}

output "invoke_url" {
  value = aws_api_gateway_stage.main.invoke_url
}
