import streamlit as st
import json
import os
import re
import boto3
from utils.auth import Auth
from config_file import Config

from strands import Agent
from strands.models import BedrockModel
from strands.agent.conversation_manager import SummarizingConversationManager

from mcp import stdio_client, StdioServerParameters
from strands.tools.mcp import MCPClient

# Text cleaning utility to fix formatting issues
def clean_markdown_text(text):
    """
    Clean markdown text to prevent formatting issues in Streamlit
    """
    if not isinstance(text, str):
        return text
    #ski the relacements
    return text
    # Fix mixed bold/italic formatting that causes issues
    # Replace problematic patterns like **text*more* with **text more**
    text = re.sub(r'\*\*([^*]+)\*([^*]+)\*\*', r'**\1 \2**', text)
    text = re.sub(r'\*\*([^*]+)\*([^*]+)\)', r'**\1 \2)**', text)
    text = re.sub(r'\*([^*]+)\*\*([^*]+)\*\*', r'*\1* **\2**', text)
    
    # Fix dollar amount formatting issues
    text = re.sub(r'\$\*\*([0-9,]+\.?[0-9]*)\*\*', r'$\1', text)
    text = re.sub(r'\$\*([0-9,]+\.?[0-9]*)\*', r'$\1', text)
    
    # Fix parentheses with mixed formatting
    text = re.sub(r'\*\*\(([^)]+)\)\*\*', r'(\1)', text)
    text = re.sub(r'\*\(([^)]+)\)\*', r'(\1)', text)
    
    # Clean up multiple consecutive formatting markers
    text = re.sub(r'\*{3,}', '**', text)
    text = re.sub(r'_{3,}', '__', text)
    
    return text

# Safe markdown display function
def safe_markdown(content):
    """Display markdown content with text cleaning"""
    st.markdown(clean_markdown_text(content))



# Initialize session state for conversation history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Initialize details placeholder and output
if "details_placeholder" not in st.session_state:
    st.session_state.details_placeholder = None
if "output" not in st.session_state:
    st.session_state.output = []

# ID of Secrets Manager containing cognito parameters
secrets_manager_id = Config.SECRETS_MANAGER_ID

# ID of the AWS region in which Secrets Manager is deployed
region = Config.DEPLOYMENT_REGION

if Config.ENABLE_AUTH:
    # Initialise CognitoAuthenticator
    authenticator = Auth.get_authenticator(secrets_manager_id, region)

    # Authenticate user, and stop here if not logged in
    is_logged_in = authenticator.login()
    if not is_logged_in:
        st.stop()

    def logout():
        authenticator.logout()

    with st.sidebar:
        # Enhanced user info display for SAML users
        try:
            user_info = authenticator.get_user_info()
            username = authenticator.get_username()
            
            # Display user information
            if user_info and user_info.get('given_name'):
                st.text(f"Welcome,\n{user_info.get('given_name')} {user_info.get('family_name', '')}")
            else:
                st.text(f"Welcome,\n{username}")
                
            if user_info and user_info.get('email'):
                st.text(f"📧 {user_info['email']}")
            
            # Show authentication method
            if Config.ENABLE_SAML_FEDERATION:
                st.text("🔐 SSO Authentication")
                
        except Exception as e:
            # Fallback to basic username display
            st.text(f"Welcome,\n{authenticator.get_username()}")
            
        st.button("Logout", "logout_btn", on_click=logout)

# Add title on the page
st.title("FinOps AI Assistant")
st.write("Your intelligent AWS cost management companion. Get cost analysis, rightsizing recommendations, and optimize your cloud spending with AI-powered insights.")

# Add sample queries
with st.expander("💡 Sample Questions to Try"):
    st.markdown("""
    **🆓 Free Tier & Budget Management:**
    - "Show me my AWS Free Tier usage status"
    - "How are my budgets performing this month?"
    - "Am I at risk of exceeding any budgets?"
    
    **💰 Cost Analysis & Forecasting:**
    - "Show me my AWS costs for the last 30 days"
    - "What are my top 5 most expensive services?"
    - "Compare my costs from last month to this month"
    - "What's driving my cost increases?"
    
    **⚡ Optimization & Recommendations:**
    - "Give me rightsizing recommendations for my EC2 instances"
    - "What Compute Optimizer recommendations do I have?"
    - "Show me cost optimization opportunities"
    - "Which instances are good candidates for Graviton migration?"
    
    **💳 Savings Plans & Reserved Instances:**
    - "What's my Reserved Instance coverage?"
    - "Give me Savings Plans recommendations"
    - "How well am I utilizing my Savings Plans?"
    
    **🗄️ Storage Optimization:**
    - "Analyze my S3 storage costs by bucket"
    - "What S3 lifecycle policy opportunities do I have?"
    - "Show me Storage Lens metrics for cost optimization"
    
    **🔍 Anomaly Detection:**
    - "Have there been any cost anomalies recently?"
    - "Set up anomaly detection for my account"
    
    **🏢 Multi-Account Analysis:**
    - "Show me costs across all my linked accounts"
    - "Which account is driving the most costs?"
    
    **🔧 Service Configuration & Investigation:**
    - "Show me details about my EC2 instances"
    - "What are the configurations of my RDS databases?"
    - "List all my S3 buckets and their properties"
    - "Investigate the security groups for my VPC"
    - "Show me Lambda function configurations and their costs"
    - "What are the tags on my expensive resources?"
    """)

# Define agent with current date context
from datetime import datetime
current_date = datetime.now().strftime("%Y-%m-%d")
current_day = datetime.now().strftime("%A")

system_prompt = f"""You are a FinOps AI Assistant, an expert in AWS cost management and cloud financial optimization. 
You help users understand their AWS spending, identify cost optimization opportunities, and make data-driven decisions about their cloud infrastructure.

**Current Date Context:**
- Today is {current_day}, {current_date}
- Use this date as reference for relative time queries like "last month", "this week", "30 days ago", etc.
- When users ask for cost data for relative periods, calculate the exact dates based on today's date

Your capabilities include:

🆓 **AWS Free Tier Management:**
- Monitor Free Tier usage to avoid unexpected charges
- Optimize usage within Free Tier limits

💰 **Cost and Usage Analysis:**
- Analyze historical and forecasted AWS costs with flexible grouping and filtering
- Track resource usage trends across AWS environments
- Compare costs between time periods with detailed breakdowns
- Identify key factors driving cost changes

📊 **Budget Management:**
- Monitor existing budgets and their performance against actual spending
- Provide budget recommendations and alerts

🔍 **Cost Anomaly Detection:**
- Identify unusual spending patterns and their root causes
- Set up anomaly detection for proactive cost management

⚡ **Cost Optimization:**
- Provide rightsizing recommendations for EC2, Lambda, EBS, and more
- Access cost-saving opportunities across the entire AWS environment
- Analyze Graviton migration opportunities

💳 **Savings Plans and Reserved Instances:**
- Analyze RI coverage and provide purchase recommendations
- Get personalized Savings Plans recommendations based on usage patterns
- Monitor Savings Plans utilization and coverage

🗄️ **S3 Storage Optimization:**
- Run SQL queries against Storage Lens metrics data
- Analyze S3 storage costs by bucket, storage class, and region
- Identify lifecycle policy opportunities and cost-saving measures

🏢 **Multi-Account Analysis:**
- Analyze costs across multiple linked accounts
- Provide consolidated cost insights for organizations

🔧 **AWS Service Configuration & Investigation:**
- Inspect detailed AWS service configurations and settings
- Analyze resource properties, tags, and metadata
- Investigate service dependencies and relationships
- Review security configurations and compliance status
- Examine operational metrics and performance data
- Deep-dive into service-specific configurations across all AWS services

Always provide actionable insights with specific dollar amounts when available. Use clear, business-friendly language and format responses with emojis and clear sections for better readability. Focus on ROI and business impact of your recommendations.

FORMATTING GUIDELINES:
- Use simple markdown formatting only (**, -, numbers for lists)
- Avoid complex nested formatting or mixed bold/italic text
- Keep dollar amounts clear: $123.45 (not $**123.45** or $*123.45*)
- Use bullet points (-) instead of complex list formatting
- Separate sections with clear headings using ##"""

# Create boto3 session using default credential chain
session = boto3.Session(region_name=os.getenv('AWS_DEFAULT_REGION', region))

# If TARGET_ROLE_ARN is provided, assume that role for cross-account access
target_role_arn = os.getenv('TARGET_ROLE_ARN')
assumed_role_credentials = None
if target_role_arn:
    print(f"Assuming role: {target_role_arn}")
    sts = session.client('sts')
    assumed_role = sts.assume_role(
        RoleArn=target_role_arn,
        RoleSessionName='finops-chatbot-session'
    )
    
    # Store credentials for MCP server
    assumed_role_credentials = assumed_role['Credentials']
    
    # Create new session with assumed role credentials
    session = boto3.Session(
        aws_access_key_id=assumed_role_credentials['AccessKeyId'],
        aws_secret_access_key=assumed_role_credentials['SecretAccessKey'],
        aws_session_token=assumed_role_credentials['SessionToken'],
        region_name=os.getenv('AWS_DEFAULT_REGION', region)
    )

# Debug credential information
print("Credential configuration:")
print(f"  AWS_DEFAULT_REGION: {os.getenv('AWS_DEFAULT_REGION', 'NOT SET')}")
print(f"  TARGET_ROLE_ARN: {'SET' if os.getenv('TARGET_ROLE_ARN') else 'NOT SET'}")
print(f"  Using credential chain: Environment vars → Container role → Instance role")
if os.getenv('AWS_ACCESS_KEY_ID'):
    print(f"  Explicit credentials detected in environment")

# Create the Bedrock model with configurable model ID
model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
print(f"Using Bedrock model: {model_id}")

model = BedrockModel(
    model_id=model_id,
    max_tokens=8192,
    region_name=region,
#    additional_request_fields={
#        "thinking": {
#            "type": "disabled",
#        }
#    },
)

# FinOps-optimized conversation manager
finops_conversation_manager = SummarizingConversationManager(
    summary_ratio=0.3,
    preserve_recent_messages=15,
    summarization_system_prompt="""
    Summarize this FinOps conversation preserving:
    - AWS cost findings and specific dollar amounts
    - Service recommendations and optimization opportunities
    - User's business goals and cost concerns
    - Key resource configurations and usage patterns
    - Important billing insights and anomalies
    
    Format as structured bullet points for financial decision-making.
    Focus on actionable insights that help with cost optimization.
    """
)

# Initialize the agent with MCP tools
if "agent" not in st.session_state:
    try:
        # Set up environment for MCP server
        mcp_env = os.environ.copy()
        mcp_env.update({
            'FASTMCP_LOG_LEVEL': 'ERROR',
            'AWS_REGION': os.getenv('AWS_DEFAULT_REGION', region),
        })
        
        # Use assumed role credentials for MCP server if available, otherwise fall back to environment
        if assumed_role_credentials:
            print("Using assumed role credentials for MCP server")
            mcp_env.update({
                'AWS_ACCESS_KEY_ID': assumed_role_credentials['AccessKeyId'],
                'AWS_SECRET_ACCESS_KEY': assumed_role_credentials['SecretAccessKey'],
                'AWS_SESSION_TOKEN': assumed_role_credentials['SessionToken'],
            })
        else:
            # Pass through AWS credentials if they exist in environment (for local testing)
            for aws_env_var in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN']:
                if os.getenv(aws_env_var):
                    mcp_env[aws_env_var] = os.getenv(aws_env_var)
        
        # Configuration options for MCP servers
        # Only using billing/cost management MCP server
        
        # Create billing MCP client
        billing_mcp_client = MCPClient(lambda: stdio_client(
            StdioServerParameters(
                command="python",
                args=["-m", "awslabs.billing_cost_management_mcp_server.server"],
                env=mcp_env
            )
        ))
        
        # Only using billing/cost management MCP server - AWS API server removed
        
        with st.spinner("🔧 Loading FinOps tools..."):
            all_tools = []
            
            # Try to start billing MCP server first
            try:
                with st.spinner("📊 Starting Billing MCP server..."):
                    billing_mcp_client.__enter__()
                    st.session_state.billing_mcp_client = billing_mcp_client
                    billing_tools = billing_mcp_client.list_tools_sync()
                    all_tools.extend(billing_tools)
                    print(f"✅ Loaded {len(billing_tools)} tools from Billing MCP server")
                    st.sidebar.success(f"✅ Billing Server: {len(billing_tools)} tools")
                    
                    # Add a small delay to let billing server fully initialize
                    import time
                    time.sleep(2)
                    
            except Exception as e:
                print(f"❌ Failed to start Billing MCP server: {e}")
                st.sidebar.error(f"❌ Billing Server Failed: {str(e)}")
            
            # Only using billing/cost management tools
            
            # Use whatever tools we successfully loaded
            raw_mcp_tools = all_tools
            print(f"✅ Total: {len(raw_mcp_tools)} tools loaded")
            
            try:
                
                # Use MCP tools directly (assuming they have underscore names)
                if raw_mcp_tools:
                    print(f"Loading {len(raw_mcp_tools)} MCP tools...")
                    
                    mcp_tools = raw_mcp_tools
                    
                    # Show debug info for tools
                    for i, tool in enumerate(raw_mcp_tools):
                        tool_name = getattr(tool, 'name', getattr(tool, 'tool_name', f'tool_{i}'))
                        
                        # Show debug info for first few tools only
                        if i < 10:
                            print(f"  Tool {i}: {tool_name} (type: {type(tool)})")
                        elif i == 10:
                            print(f"  ... and {len(raw_mcp_tools) - 10} more tools")
                    
                    print(f"✅ Loaded {len(mcp_tools)} MCP tools")
                    
                    # Display available tools in sidebar
                    st.sidebar.success(f"✅ {len(mcp_tools)} FinOps Tools Loaded")
                    with st.sidebar.expander("🔧 Available Tools"):
                        for tool in mcp_tools:
                            tool_name = getattr(tool, 'name', getattr(tool, 'tool_name', str(tool)))
                            st.write(f"• {tool_name}")
                    

                    
                    # Create agent with MCP tools and conversation manager
                    st.session_state.agent = Agent(
                        model=model,
                        system_prompt=system_prompt,
                        tools=mcp_tools,
                        conversation_manager=finops_conversation_manager,
                    )
                    
                else:
                    # No tools available
                    st.sidebar.warning("⚠️ No MCP tools loaded")
                    st.session_state.agent = Agent(
                        model=model,
                        system_prompt=system_prompt,
                        tools=[],
                        conversation_manager=finops_conversation_manager,
                    )
                    
            except Exception as e:
                print(f"❌ Error loading MCP tools: {e}")
                st.sidebar.error(f"❌ MCP Tools Error: {str(e)}")
                # Fallback agent without MCP tools
                st.session_state.agent = Agent(
                    model=model,
                    system_prompt=system_prompt,
                    tools=[],
                    conversation_manager=finops_conversation_manager,
                )
                
    except Exception as e:
        st.sidebar.error(f"❌ Agent initialization error: {str(e)}")
        print(f"❌ Agent initialization error: {e}")
        # Fallback agent
        st.session_state.agent = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=[],
            conversation_manager=finops_conversation_manager,
        )

# Keep track of the number of previous messages in the agent flow
if "start_index" not in st.session_state:
    st.session_state.start_index = 0

# Add simple control buttons to sidebar
with st.sidebar:
    st.markdown("---")
    st.subheader("� Conterols")
    
    if st.button("🆕 Fresh Chat"):
        # Clear conversation history
        st.session_state.messages = []
        if hasattr(st.session_state, 'agent') and st.session_state.agent:
            st.session_state.agent.messages = []
        st.session_state.start_index = 0
        st.success("Started fresh conversation!")
        st.rerun()

# Display old chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.empty()  # This forces the container to render without adding visible content (workaround for streamlit bug)
        if message.get("type") == "tool_use":
            st.code(message["content"])
        else:
            st.markdown(clean_markdown_text(message["content"]))

# Chat input
if prompt := st.chat_input("Ask your agent..."):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display user message
    with st.chat_message("user"):
        st.write(prompt)

    # Prepare containers for response
    with st.chat_message("assistant"):
        # Always create a fresh placeholder for this conversation
        details_placeholder = st.empty()
        st.session_state.details_placeholder = details_placeholder
    
    # Initialize strings to store streaming of model output
    st.session_state.output = []

    # Create a streaming callback handler that displays content in real-time
    # We'll use both a buffer for final display and real-time streaming
    output_buffer = []
    
    def custom_callback_handler(**kwargs):
        try:
            # Just collect data in buffer without trying to display in real-time
            if "data" in kwargs:
                # Add or append data to buffer
                if len(output_buffer) == 0 or output_buffer[-1]["type"] != "data":
                    output_buffer.append({"type": "data", "content": kwargs["data"]})
                else:
                    output_buffer[-1]["content"] += kwargs["data"]
                    
            elif "current_tool_use" in kwargs and kwargs["current_tool_use"].get("name"):
                tool_use_text = "Using tool: " + kwargs["current_tool_use"]["name"] + " with args: " + str(kwargs["current_tool_use"]["input"])
                output_buffer.append({"type": "tool_use", "content": tool_use_text})
                
            elif "reasoningText" in kwargs:
                # Add or append reasoning
                if len(output_buffer) == 0 or output_buffer[-1]["type"] != "reasoning":
                    output_buffer.append({"type": "reasoning", "content": kwargs["reasoningText"]})
                else:
                    output_buffer[-1]["content"] += kwargs["reasoningText"]
                    
        except Exception as e:
            print(f"Error in callback handler: {e}")
            print(f"Callback kwargs: {kwargs}")
    
    # Set callback handler into the agent
    st.session_state.agent.callback_handler = custom_callback_handler
    
    # Get response from agent
    response = st.session_state.agent(prompt)
    
    # Copy buffer to session state for display
    st.session_state.output = output_buffer.copy()
    
    # Display the response after completion
    with details_placeholder.container():
        for item in output_buffer:
            if item["type"] == "data":
                st.markdown(clean_markdown_text(item["content"]))
            elif item["type"] == "tool_use":
                st.code(item["content"])
            elif item["type"] == "reasoning":
                st.markdown(item["content"])
    
    # Add assistant messages to chat history
    if st.session_state.output:
        for output_item in st.session_state.output:
            st.session_state.messages.append({"role": "assistant", "type": output_item["type"], "content": output_item["content"]})

# Cleanup function for MCP client (called when session ends)
def cleanup_mcp_clients():
    if "billing_mcp_client" in st.session_state:
        try:
            st.session_state.billing_mcp_client.__exit__(None, None, None)
            print("🧹 Billing MCP client session closed")
        except Exception as e:
            print(f"⚠️ Error closing Billing MCP client: {e}")
    
    # AWS API MCP client removed - only using billing MCP server

# Register cleanup function
import atexit
atexit.register(cleanup_mcp_clients)