import os
import json
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class AegisAIGateway:
    # Watch out tenant is accepted blindly must fix pronto!!!!!
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.primary_region = os.getenv("AWS_REGION", "us-east-1")
        self.fallback_region = os.getenv("FALLBACK_REGION", "eu-west-1")
        
        # Default: Cross-Region Inference Profile ID for Claude 3.5 Sonnet
        self.model_id = os.getenv(
            "AI_MODEL_ID", 
            "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
        )
        self.guardrail_id = os.getenv("BEDROCK_GUARDRAIL_ID")
        self.guardrail_version = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")

        self.bedrock_client = boto3.client(
            service_name="bedrock-runtime",
            region_name=self.primary_region
        )

    def _build_payload(self, user_prompt: str) -> str:
        return json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user", 
                    "content": user_prompt
                }
            ]
        })

    def process_and_stream_prompt(self, user_prompt: str):
        """
        Executes the invocation with response stream.
        Uses Bedrock Guardrails directly in the invocation to check DLP/PII without TTFT penalty.
        """
        body = self._build_payload(user_prompt)
        # WARNING:
        # DRAFT in production? Cannot be please change this love:)
        invoke_params = {
            "modelId": self.model_id,
            "body": body
        }

        # Guardrails inspect PII & prompt injection directly in the Bedrock stream
        if self.guardrail_id:
            invoke_params["guardrailIdentifier"] = self.guardrail_id
            invoke_params["guardrailVersion"] = self.guardrail_version
            invoke_params["trace"] = "ENABLED"

        try:
            logger.info(f"Invoking Bedrock for tenant: {self.tenant_id} in {self.primary_region}")
            response = self.bedrock_client.invoke_model_with_response_stream(**invoke_params)
            return response.get("body")

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            
            # Automatic failover on throttling (429 / ThrottlingException)
            if error_code in ["ThrottlingException", "TooManyRequestsException"]:
                logger.warning(f"Throttling in {self.primary_region} for tenant {self.tenant_id}. Triggering fallback to {self.fallback_region}...")
                return self._trigger_cross_region_fallback(invoke_params)
            
            logger.error(f"Bedrock invocation failed: {str(e)}")
            raise e

    def _trigger_cross_region_fallback(self, invoke_params: dict):
        """
        Stateful fallback client targeting the secondary AWS region.
        """
        fallback_client = boto3.client(
            service_name="bedrock-runtime",
            region_name=self.fallback_region
        )
        response = fallback_client.invoke_model_with_response_stream(**invoke_params)
        return response.get("body")

    def generate_text_stream(self, user_prompt: str):
        """
        Generator that reads chunks from the Bedrock EventStream and yields chunks as text.
        """
        event_stream = self.process_and_stream_prompt(user_prompt)
        
        for event in event_stream:
            # Bugged:
            # If Bedrock breaks in the middle or pushes an error event into the stream, this is simply ignored instead of being terminated cleanly.
            chunk = event.get("chunk")
            if chunk:
                chunk_json = json.loads(chunk.get("bytes").decode("utf-8"))
                
                # Claude 3 streaming format
                if chunk_json.get("type") == "content_block_delta":
                    delta = chunk_json.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield delta.get("text", "")


def lambda_handler(event, context):
    """
    AWS Lambda entry point.
    Extracts payload and tenant headers, then executes the gateway invocation.
    """
    try:
        # Extraction of headers and payload
        headers = event.get("headers", {}) or {}
        tenant_id = headers.get("x-tenant-id", "tenant-default")

        body_str = event.get("body", "{}")
        if isinstance(body_str, str):
            body_data = json.loads(body_str) if body_str else {}
        else:
            body_data = body_str

        user_prompt = body_data.get("prompt")
        if not user_prompt:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Missing 'prompt' in request body."})
            }

        gateway = AegisAIGateway(tenant_id=tenant_id)
        
        # Aggregate complete response (for standard REST invocations)
        # If Lambda Function URL response streaming is used, the stream can be iterated directly.
        collected_response = "".join(list(gateway.generate_text_stream(user_prompt)))

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "X-Tenant-ID": tenant_id
            },
            "body": json.dumps({
                "tenant_id": tenant_id,
                "completion": collected_response
            })
        }
#
    except Exception as e:
        logger.error(f"Internal Handler Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)})
        }