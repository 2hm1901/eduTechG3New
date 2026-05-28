variable "region" {
  type    = string
  default = "ap-southeast-2"
}

variable "env" {
  type    = string
  default = "hackathon"
}

variable "upload_handler_zip" {
  type        = string
  description = "Path to the upload handler Lambda zip file"
  default     = "./lambda_placeholder/upload_handler.zip"
}

variable "text_extraction_zip" {
  type        = string
  description = "Path to the text extraction Lambda zip file"
  default     = "./lambda_placeholder/text_extraction.zip"
}

variable "chat_zip" {
  type        = string
  description = "Path to the chat Lambda zip file"
  default     = "./lambda_placeholder/chat.zip"
}

variable "summarize_quiz_zip" {
  type        = string
  description = "Path to the summarize/quiz Lambda zip file"
  default     = "./lambda_placeholder/summarize_quiz.zip"
}

variable "dashboard_zip" {
  type        = string
  description = "Path to the dashboard Lambda zip file"
  default     = "./lambda_placeholder/dashboard.zip"
}

variable "api_backend_zip" {
  type        = string
  description = "Path to the FastAPI backend Lambda zip file"
  default     = "./lambda_api/api_backend.zip"
}

variable "pypdf_layer_arn" {
  type        = string
  description = "ARN of the pypdf Lambda layer"
  default     = null
}

variable "pdf_cors_allowed_origin" {
  type        = string
  description = "Allowed origin for PDF bucket CORS"
  default     = "*"
}

variable "bedrock_model_arn" {
  type    = string
  default = ""
}

variable "bedrock_model_id" {
  type    = string
  default = "global.amazon.nova-2-lite-v1:0"
}

variable "bedrock_embedding_model_arn" {
  type    = string
  default = "arn:aws:bedrock:ap-southeast-2::foundation-model/amazon.titan-embed-text-v2:0"
}

variable "bedrock_kb_id" {
  type        = string
  description = "Bedrock Knowledge Base ID (manual)"
  default     = "FLRX3KJYII"
}

variable "bedrock_datasource_id" {
  type        = string
  description = "Bedrock Data Source ID (manual)"
  default     = "HSBK4AKJXO"
}

variable "bedrock_kb_role_name" {
  type        = string
  description = "IAM role name used by the manual Bedrock Knowledge Base"
  default     = "AmazonBedrockExecutionRoleForKnowledgeBase_ju45k"
}


variable "cors_origin" {
  type        = string
  description = "Allowed CORS origin for API Gateway and backend"
  default     = "*"
}
