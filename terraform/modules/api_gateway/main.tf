data "aws_region" "current" {}

resource "aws_api_gateway_rest_api" "main" {
  name = "ai-study-buddy-api"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_authorizer" "cognito" {
  name            = "cognito-jwt-authorizer"
  rest_api_id     = aws_api_gateway_rest_api.main.id
  type            = "COGNITO_USER_POOLS"
  provider_arns   = [var.user_pool_arn]
  identity_source = "method.request.header.Authorization"
}

resource "aws_api_gateway_resource" "upload_pdf" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "upload-pdf"
}

resource "aws_api_gateway_resource" "chat" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "chat"
}

resource "aws_api_gateway_resource" "summarize" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "summarize"
}

resource "aws_api_gateway_resource" "quiz" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "quiz"
}

resource "aws_api_gateway_resource" "dashboard" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "dashboard"
}

resource "aws_api_gateway_resource" "api_root" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "api"
}

resource "aws_api_gateway_resource" "api_proxy" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.api_root.id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_resource" "health" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "health"
}

resource "aws_api_gateway_method" "upload_pdf" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.upload_pdf.id
  http_method   = "POST"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_method" "chat" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.chat.id
  http_method   = "POST"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_method" "summarize" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.summarize.id
  http_method   = "POST"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_method" "quiz" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.quiz.id
  http_method   = "POST"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_method" "dashboard" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.dashboard.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_method" "api_proxy" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.api_proxy.id
  http_method   = "ANY"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_method" "health" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.health.id
  http_method   = "GET"
  authorization = "NONE"
}

locals {
  cors_headers = {
    "Access-Control-Allow-Origin"  = "'${var.cors_origin}'"
    "Access-Control-Allow-Headers" = "'Authorization,Content-Type,X-User-Id'"
    "Access-Control-Allow-Methods" = "'OPTIONS,GET,POST,PATCH,PUT,DELETE'"
  }
}

resource "aws_api_gateway_method" "options" {
  for_each = {
    upload_pdf = aws_api_gateway_resource.upload_pdf.id
    chat       = aws_api_gateway_resource.chat.id
    summarize  = aws_api_gateway_resource.summarize.id
    quiz       = aws_api_gateway_resource.quiz.id
    dashboard  = aws_api_gateway_resource.dashboard.id
    api_proxy  = aws_api_gateway_resource.api_proxy.id
    health     = aws_api_gateway_resource.health.id
  }

  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = each.value
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options" {
  for_each = aws_api_gateway_method.options

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = each.value.resource_id
  http_method = each.value.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options" {
  for_each = aws_api_gateway_method.options

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = each.value.resource_id
  http_method = each.value.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = true
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
  }
}

resource "aws_api_gateway_integration_response" "options" {
  for_each = aws_api_gateway_method.options

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = each.value.resource_id
  http_method = each.value.http_method
  status_code = aws_api_gateway_method_response.options[each.key].status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = local.cors_headers["Access-Control-Allow-Origin"]
    "method.response.header.Access-Control-Allow-Headers" = local.cors_headers["Access-Control-Allow-Headers"]
    "method.response.header.Access-Control-Allow-Methods" = local.cors_headers["Access-Control-Allow-Methods"]
  }
}

locals {
  upload_uri    = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${var.upload_handler_arn}/invocations"
  chat_uri      = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${var.chat_arn}/invocations"
  summarize_uri = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${var.summarize_quiz_arn}/invocations"
  quiz_uri      = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${var.summarize_quiz_arn}/invocations"
  dashboard_uri = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${var.dashboard_arn}/invocations"
  api_backend_uri = "arn:aws:apigateway:${data.aws_region.current.name}:lambda:path/2015-03-31/functions/${var.api_backend_arn}/invocations"
}

resource "aws_api_gateway_integration" "upload_pdf" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.upload_pdf.id
  http_method             = aws_api_gateway_method.upload_pdf.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = local.upload_uri
}

resource "aws_api_gateway_integration" "chat" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.chat.id
  http_method             = aws_api_gateway_method.chat.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = local.chat_uri
}

resource "aws_api_gateway_integration" "summarize" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.summarize.id
  http_method             = aws_api_gateway_method.summarize.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = local.summarize_uri
}

resource "aws_api_gateway_integration" "quiz" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.quiz.id
  http_method             = aws_api_gateway_method.quiz.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = local.quiz_uri
}

resource "aws_api_gateway_integration" "dashboard" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.dashboard.id
  http_method             = aws_api_gateway_method.dashboard.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = local.dashboard_uri
}

resource "aws_api_gateway_integration" "api_proxy" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.api_proxy.id
  http_method             = aws_api_gateway_method.api_proxy.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = local.api_backend_uri
}

resource "aws_api_gateway_integration" "health" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.health.id
  http_method             = aws_api_gateway_method.health.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = local.api_backend_uri
}

resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  depends_on = [
    aws_api_gateway_integration.upload_pdf,
    aws_api_gateway_integration.chat,
    aws_api_gateway_integration.summarize,
    aws_api_gateway_integration.quiz,
    aws_api_gateway_integration.dashboard,
    aws_api_gateway_integration.api_proxy,
    aws_api_gateway_integration.health,
    aws_api_gateway_integration.options,
    aws_api_gateway_integration_response.options,
  ]

  triggers = {
    redeploy = sha1(jsonencode([
      aws_api_gateway_resource.upload_pdf.id,
      aws_api_gateway_resource.chat.id,
      aws_api_gateway_resource.summarize.id,
      aws_api_gateway_resource.quiz.id,
      aws_api_gateway_resource.dashboard.id,
      aws_api_gateway_resource.api_proxy.id,
      aws_api_gateway_resource.health.id,
      aws_api_gateway_method.upload_pdf.id,
      aws_api_gateway_method.chat.id,
      aws_api_gateway_method.summarize.id,
      aws_api_gateway_method.quiz.id,
      aws_api_gateway_method.dashboard.id,
      aws_api_gateway_method.api_proxy.id,
      aws_api_gateway_method.health.id,
      aws_api_gateway_method.options["upload_pdf"].id,
      aws_api_gateway_method.options["chat"].id,
      aws_api_gateway_method.options["summarize"].id,
      aws_api_gateway_method.options["quiz"].id,
      aws_api_gateway_method.options["dashboard"].id,
      aws_api_gateway_method.options["api_proxy"].id,
      aws_api_gateway_method.options["health"].id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "main" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  deployment_id = aws_api_gateway_deployment.main.id
  stage_name    = var.stage_name
}

resource "aws_api_gateway_gateway_response" "default_4xx" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  response_type = "DEFAULT_4XX"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = local.cors_headers["Access-Control-Allow-Origin"]
    "gatewayresponse.header.Access-Control-Allow-Headers" = local.cors_headers["Access-Control-Allow-Headers"]
    "gatewayresponse.header.Access-Control-Allow-Methods" = local.cors_headers["Access-Control-Allow-Methods"]
  }
}

resource "aws_api_gateway_gateway_response" "default_5xx" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  response_type = "DEFAULT_5XX"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = local.cors_headers["Access-Control-Allow-Origin"]
    "gatewayresponse.header.Access-Control-Allow-Headers" = local.cors_headers["Access-Control-Allow-Headers"]
    "gatewayresponse.header.Access-Control-Allow-Methods" = local.cors_headers["Access-Control-Allow-Methods"]
  }
}
