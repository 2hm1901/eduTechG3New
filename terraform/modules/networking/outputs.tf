output "vpc_id" {
  value = aws_vpc.main.id
}

output "private_subnet_id" {
  value = aws_subnet.private.id
}

output "lambda_security_group_id" {
  value = aws_security_group.lambda.id
}

output "endpoints_security_group_id" {
  value = aws_security_group.endpoints.id
}
