class Config:
    # Stack name - Updated for FinOps Chatbot
    # Change this value if you want to create a new instance of the stack
    STACK_NAME = "FinOps-AI-Chatbot"
    
    # Put your own custom value here to prevent ALB to accept requests from
    # other clients that CloudFront. You can choose any random string.
    CUSTOM_HEADER_VALUE = "FinOps_Chatbot_Security_Header_2024"    
    
    # ID of Secrets Manager containing cognito parameters
    # When you delete a secret, you cannot create another one immediately
    # with the same name. Change this value if you destroy your stack and need
    # to recreate it with the same STACK_NAME.
    SECRETS_MANAGER_ID = f"{STACK_NAME}ParamCognitoSecret987654321"

    # AWS region in which you want to deploy the cdk stack
    DEPLOYMENT_REGION = "us-east-1"

    # Enable authentication (recommended for production)
    ENABLE_AUTH = True  # Enabled for production deployment

    # SAML Federation Settings
    ENABLE_SAML_FEDERATION = False  # Temporarily disabled until Identity Center setup is complete
    IDENTITY_CENTER_REGION = "eu-central-1"  # Your Identity Center region
    
    # These will be populated after Identity Center app setup
    SAML_METADATA_URL = ""  # Will be provided by Identity Center after app creation
    SAML_PROVIDER_NAME = "AWSIdentityCenter"
    
    # Optional: Custom domain for better UX (disabled to avoid conflicts)
    COGNITO_CUSTOM_DOMAIN = ""  # Disabled to avoid domain conflicts

    # Bedrock Model Configuration
    # Default model for the FinOps AI Chatbot
    # Can be overridden via BEDROCK_MODEL_ID environment variable
    DEFAULT_BEDROCK_MODEL = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    #DEFAULT_BEDROCK_MODEL = "us.amazon.nova-pro-v1:0"
