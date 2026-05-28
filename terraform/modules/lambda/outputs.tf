output "upload_handler_arn" {
  value = aws_lambda_function.upload_handler.arn
}

output "text_extraction_arn" {
  value = aws_lambda_function.text_extraction.arn
}

output "chat_arn" {
  value = aws_lambda_function.chat.arn
}

output "summarize_quiz_arn" {
  value = aws_lambda_function.summarize_quiz.arn
}

output "dashboard_arn" {
  value = aws_lambda_function.dashboard.arn
}

output "api_backend_arn" {
  value = aws_lambda_function.api_backend.arn
}

output "upload_handler_name" {
  value = aws_lambda_function.upload_handler.function_name
}

output "text_extraction_name" {
  value = aws_lambda_function.text_extraction.function_name
}

output "upload_handler_role_arn" {
  value = aws_iam_role.upload_handler.arn
}

output "text_extraction_role_arn" {
  value = aws_iam_role.text_extraction.arn
}

output "api_backend_role_arn" {
  value = aws_iam_role.api_backend.arn
}

output "lambda_names" {
  value = [
    aws_lambda_function.upload_handler.function_name,
    aws_lambda_function.text_extraction.function_name,
    aws_lambda_function.chat.function_name,
    aws_lambda_function.summarize_quiz.function_name,
    aws_lambda_function.dashboard.function_name,
    aws_lambda_function.api_backend.function_name,
  ]
}

output "lambda_timeouts" {
  value = {
    (aws_lambda_function.upload_handler.function_name)  = 60
    (aws_lambda_function.text_extraction.function_name) = 300
    (aws_lambda_function.chat.function_name)            = 30
    (aws_lambda_function.summarize_quiz.function_name)  = 60
    (aws_lambda_function.dashboard.function_name)       = 15
    (aws_lambda_function.api_backend.function_name)     = 30
  }
}
