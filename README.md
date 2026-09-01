Aegis AI Gateway & Flow GovernanceA serverless, high-availability AI gateway proxy built on AWS Lambda, AWS Bedrock, and Terraform. It acts as a secure intermediary between client applications and Large Language Models (Claude 3.5 Sonnet), featuring automated cross-region failover and integrated safety guardrails.Key FeaturesCross-Region Failover: Automatically detects API throttling (429, ThrottlingException) in the primary region (us-east-1) and seamlessly routes requests to the secondary fallback region (eu-west-1) without interrupting client workflows.Integrated Safety Guardrails: Direct integration with AWS Bedrock Guardrails in the invocation path for real-time PII detection, Data Loss Prevention (DLP), and prompt injection mitigation without added pre-processing latency.Multi-Tenancy Support: Extracts and tracks tenant metadata via the x-tenant-id header for tenant-aware logging and routing.Infrastructure as Code (IaC): Fully automated deployment of all cloud components using Terraform (least-privilege IAM policies, Lambda function URLs, configured timeouts).Project StructurePlaintext.
├── ai_gateway.py                   # Lambda handler & Gateway implementation (Python 3.11)
├── main.tf                         # Terraform infrastructure definition
├── requirements.txt                # Python dependencies (boto3, botocore)
└── README.md                       # Project documentation
PrerequisitesAWS CLI configured with appropriate permissions and active Bedrock model access for Anthropic Claude 3.5 Sonnet.Terraform >= 1.5.0Python 3.11+ConfigurationThe gateway behavior is controlled via environment variables (configured in main.tf or the AWS Lambda console):VariableDefault ValueDescriptionAWS_REGIONus-east-1Primary AWS region for Bedrock invocationsFALLBACK_REGIONeu-west-1Secondary AWS region for failover during rate limits/throttlingAI_MODEL_IDus.anthropic.claude-3-5-sonnet-20240620-v1:0Bedrock inference profile or model IDBEDROCK_GUARDRAIL_ID""Optional: Identifier for the AWS Bedrock GuardrailBEDROCK_GUARDRAIL_VERSION1Version tag for the assigned Bedrock GuardrailDeployment1. Prepare the deployment packagePackage the Lambda function into a ZIP archive:Bashzip lambda_function_payload.zip ai_gateway.py
2. Provision infrastructure with TerraformBash# Initialize Terraform
terraform init

# Review execution plan
terraform plan

# Apply changes
terraform apply -auto-approve
Upon successful execution, Terraform outputs the public lambda_function_url.API UsageSend HTTP POST requests with a JSON payload to the generated Function URL.Example Request (cURL)Bashcurl -X POST "https://<YOUR-LAMBDA-FUNCTION-URL>.lambda-url.us-east-1.on.aws/" \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: tenant-corp-42" \
  -d '{
    "prompt": "Provide a brief executive summary of GDPR data compliance requirements."
  }'
Example ResponseJSON{
  "tenant_id": "tenant-corp-42",
  "completion": "The General Data Protection Regulation (GDPR) mandates strict guidelines on the collection, processing, and storage of personal data..."
}
Production Security ConsiderationsAuthentication: The provided template configures authorization_type = "NONE". For production environments, switch to AWS_IAM or front the function with an API Gateway using Cognito / JWT Authorizers.CORS Restrictions: Restrict allow_origins = ["*"] in main.tf to authorized frontend domain names to prevent cross-origin abuse.
