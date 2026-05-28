variable "lambda_names" {
  type = list(string)
}

variable "lambda_timeouts" {
  type = map(number)
}

variable "dynamodb_table_name" {
  type = string
}
