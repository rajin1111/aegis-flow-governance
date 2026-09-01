# main.tf - Aegis Flow Infrastructure via Terraform

terraform {
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

# 1. IAM-Rolle für die Lambda-Steuerung
resource "aws_iam_role" "lambda_role" {
  name = "aegis_gateway_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "://amazonaws.com" }
    }]
  })
}

# 2. IAM-Policy: Erlaubt Lambda den Zugriff auf Amazon Bedrock Streaming
resource "aws_iam_role_policy" "bedrock_policy" {
  name = "aegis_bedrock_streaming_policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModelWithResponseStream"]
      Resource = "*" # Für den Summit: Muss noch auf Claude-ARN begrenzt werden!
    }]
  })
}

# 3. AWS Lambda Funktion für das AI-Gateway
resource "aws_lambda_function" "ai_gateway" {
  filename      = "lambda_function_payload.zip" # Lokaler Platzhalter
  function_name = "aegis-ai-gateway-proxy"
  role          = aws_iam_role.lambda_role.arn
  handler       = "ai_gateway.lambda_handler"
  runtime       = "python3.11"
  timeout       = 30

  environment {
    variables = {
      AI_MODEL_ID = "anthropic.claude-3-5-sonnet-v1:0"
    }
  }
}