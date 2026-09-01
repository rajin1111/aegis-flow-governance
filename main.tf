# main.tf - Aegis Flow AWS infrastructure

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# All resources are currently deployed in us-east-1 (for reasons see README.md)
provider "aws" {
  region = "us-east-1"
}
S
# Execution role used by the AI Gateway Lambda
resource "aws_iam_role" "lambda_role" {
  name = "aegis_gateway_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"

    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"

      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Allows Lambda to write logs to CloudWatch
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Allows streaming inference and Guardrail checks through Bedrock
# TODO: Restrict these wildcard ARNs before production
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

# Main gateway between th client application and Amazon Bedrock
resource "aws_lambda_function" "ai_gateway" {
  filename         = "lambda_function_payload.zip"
  source_code_hash = filebase64sha256("lambda_function_payload.zip")
  function_name    = "aegis-ai-gateway-proxy"
  role             = aws_iam_role.lambda_role.arn
  handler          = "ai_gateway.lambda_handler"
  runtime          = "python3.11"
  memory_size      = 512

  # Allows enough time for longer model responses
  timeout = 90

  environment {
    variables = {
      AI_MODEL_ID = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"

      PRIMARY_BEDROCK_REGION  = "us-east-1"
      FALLBACK_BEDROCK_REGION = "eu-west-1"

      # Leave empty to run without a Bedrock Guardrail
      BEDROCK_GUARDRAIL_ID      = ""
      BEDROCK_GUARDRAIL_VERSION = "1"
    }
  }
}

# Public streaming endpoint for the current prototype
resource "aws_lambda_function_url" "ai_gateway_url" {
  function_name      = aws_lambda_function.ai_gateway.function_name
  authorization_type = "NONE"
  invoke_mode        = "RESPONSE_STREAM"

  cors {
    allow_credentials = false
    allow_origins     = ["*"]
    allow_methods     = ["POST", "OPTIONS"]

    allow_headers = [
      "content-type",
      "x-tenant-id",
      "authorization"
    ]

    max_age = 86400
  }
}

# Displays the endpoint after deployment
output "lambda_function_url" {
  description = "Streaming endpoint of the Aegis Flow gateway"
  value       = aws_lambda_function_url.ai_gateway_url.function_url
}