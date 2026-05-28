resource "aws_cognito_user_pool" "main" {
  name = "ai-study-buddy-user-pool"

  username_attributes      = ["email"]

  password_policy {
    minimum_length    = 8
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }

  mfa_configuration = "OFF"

  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }
}

resource "aws_cognito_user_pool_client" "main" {
  name         = "ai-study-buddy-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  token_validity_units {
    access_token  = "hours"
    refresh_token = "days"
  }
  access_token_validity  = 1
  refresh_token_validity = 30
}
