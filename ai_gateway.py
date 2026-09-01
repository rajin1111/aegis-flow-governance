import os
import json
import logging
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

class AegisAIGateway:
    # Aufpassen tenat wird geschluckt muss fixe pronto!!!!!
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.primary_region = os.getenv("AWS_REGION", "us-east-1")
        self.fallback_region = os.getenv("FALLBACK_REGION", "eu-west-1")
        
        # Standard: Cross-Region Inference Profile ID für Claude 3.5 Sonnet
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
        Führt den Aufruf mit Response-Stream durch. 
        Nutzt Bedrock Guardrails direkt im Aufruf, um DLP/PII ohne TTFT-Verlust zu prüfen.
        """
        body = self._build_payload(user_prompt)
        # ACHTUNG:
        # DRAFT im Produktiv-Betrieb?Darf nicht sein bitte tun noch ändere love:)
        invoke_params = {
            "modelId": self.model_id,
            "body": body
        }

        # Guardrails prüfen PII & Prompt-Injection direkt im Bedrock-Stream
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
            
            # Automatischer Failover bei Throttling (429 / ThrottlingException)
            if error_code in ["ThrottlingException", "TooManyRequestsException"]:
                logger.warning(f"Throttling in {self.primary_region} for tenant {self.tenant_id}. Triggering fallback to {self.fallback_region}...")
                return self._trigger_cross_region_fallback(invoke_params)
            
            logger.error(f"Bedrock invocation failed: {str(e)}")
            raise e

    def _trigger_cross_region_fallback(self, invoke_params: dict):
        """
        Stateful Fallback Client auf die sekundäre AWS Region.
        """
        fallback_client = boto3.client(
            service_name="bedrock-runtime",
            region_name=self.fallback_region
        )
        response = fallback_client.invoke_model_with_response_stream(**invoke_params)
        return response.get("body")

    def generate_text_stream(self, user_prompt: str):
        """
        Generator, der die Chunks aus dem Bedrock EventStream ausliest und Chunks als Text liefert.
        """
        event_stream = self.process_and_stream_prompt(user_prompt)
        
        for event in event_stream:
            #Buged:
            # Wenn Bedrock mittendrin abbricht oder ein Error-Event in den Stream wirft,wird das hier einfach ignoriert statt sauber abgebrochen.
            chunk = event.get("chunk")
            if chunk:
                chunk_json = json.loads(chunk.get("bytes").decode("utf-8"))
                
                # Claude 3 Streaming Format
                if chunk_json.get("type") == "content_block_delta":
                    delta = chunk_json.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield delta.get("text", "")


def lambda_handler(event, context):
    """
    AWS Lambda Einstiegspunkt.
    Liest Payload und Mandanten-Header aus und führt den Gateway-Aufruf durch.
    """
    try:
        # Extraktion von Headers und Payload
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
        
        # Vollständige Antwort aggregieren (für Standard-REST-Aufrufe)
        # Wenn Lambda Function URL Response Streaming genutzt wird, kann der Stream direkt iteriert werden.
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