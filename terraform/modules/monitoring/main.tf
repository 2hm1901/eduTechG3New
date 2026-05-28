resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = toset(var.lambda_names)
  name              = "/aws/lambda/${each.key}"
  retention_in_days = 14
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each            = toset(var.lambda_names)
  alarm_name          = "${each.key}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  dimensions = {
    FunctionName = each.key
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  for_each            = toset(var.lambda_names)
  alarm_name          = "${each.key}-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  dimensions = {
    FunctionName = each.key
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  for_each            = var.lambda_timeouts
  alarm_name          = "${each.key}-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Average"
  threshold           = each.value * 0.8 * 1000
  dimensions = {
    FunctionName = each.key
  }
}

resource "aws_cloudwatch_metric_alarm" "dynamodb_system_errors" {
  alarm_name          = "ai-study-buddy-dynamodb-system-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "SystemErrors"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  dimensions = {
    TableName = var.dynamodb_table_name
  }
}
