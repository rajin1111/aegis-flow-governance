# main.tf - Aegis Flow Infrastructure via Terraform

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# 1. IAM-Rolle für die Lambda-Ausführung
resource "aws_iam_role" "lambda_role" {
  name = "aegis_gateway_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { 
        Service = "lambda.amazonaws.com" 
      }
    }]
  })
}

# 2. CloudWatch Logs Berechtigung für Lambda
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# 3. IAM-Policy: Erlaubt Lambda den Zugriff auf Bedrock Streaming & Guardrails (us-east-1 und Fallback eu-west-1)
resource "aws_iam_role_policy" "bedrock_policy" {
  name = "aegis_bedrock_streaming_policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:ApplyGuardrail"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/*",
          "arn:aws:bedrock:*:*:inference-profile/*",
          "arn:aws:bedrock:*:*:guardrail/*"
        ]
      }
    ]
  })
}

# 4. AWS Lambda Funktion für das AI-Gateway
resource "aws_lambda_function" "ai_gateway" {
  filename         = "lambda_function_payload.zip"
  function_name    = "aegis-ai-gateway-proxy"
  role             = aws_iam_role.lambda_role.arn
  handler          = "ai_gateway.lambda_handler"
  runtime          = "python3.11"
  memory_size      = 512
  timeout          = 90 # 90 Sekunden Timeout für lange Token-Generierung

  environment {
    variables = {
      AI_MODEL_ID               = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
      AWS_REGION                = "us-east-1"
      FALLBACK_REGION           = "eu-west-1"
      BEDROCK_GUARDRAIL_ID      = "" # Optional: Guardrail ID hier eintragen
      BEDROCK_GUARDRAIL_VERSION  = "1"
    }
  }
}

# 5. Lambda Function URL mit nativem Streaming-Modus (Time-to-First-Token optimiert)
resource "aws_lambda_function_url" "ai_gateway_url" {
  function_name      = aws_lambda_function.ai_gateway.function_name
  authorization_type = "NONE" # Für Produktion auf "AWS_IAM" umstellen
  invoke_mode        = "RESPONSE_STREAM"

  cors {
    allow_credentials = true
    allow_origins     = ["*"]
    allow_methods     = ["POST", "OPTIONS"]
    allow_headers     = ["content-type", "x-tenant-id", "authorization"]
    max_age           = 86400
  }
}

output "lambda_function_url" {
  description = "Die HTTP-URL für das direkte Streaming des AI-Gateways"
  value       = aws_lambda_function_url.ai_gateway_url.function_url
}