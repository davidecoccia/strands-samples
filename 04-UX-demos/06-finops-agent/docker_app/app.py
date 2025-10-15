import streamlit as st
import json
import os
import boto3
from utils.auth import Auth
from config_file import Config

from strands import Agent
from strands.models import BedrockModel
from strands.agent.conversation_manager import SummarizingConversationManager


from mcp import stdio_client, StdioServerParameters
from strands.tools.mcp import MCPClient
import re

# Text cleaning utility to fix formatting issues
def clean_markdown_text(text):
    """
    Clean markdown text to prevent formatting issues in Streamlit
    """
    if not isinstance(text, str):
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

# Token counting utility
def estimate_tokens_from_text(text):
    """
    Estimate token count from text using a more accurate method.
    Uses character count with better averages for different content types.
    """
    if not text:
        return 0
    
    # Convert to string if not already
    text_str = str(text)
    
    # Better estimation based on content type
    # Technical/JSON content: ~2.5 chars per token
    # Regular text: ~3.5 chars per token
    # We'll use 3.2 as a reasonable average
    return max(1, len(text_str) // 3.2)

def calculate_conversation_tokens(agent_messages, system_prompt):
    """
    Calculate total tokens for the entire conversation that gets sent to the LLM.
    This includes system prompt + all conversation history.
    """
    total_tokens = 0
    
    # Add system prompt tokens
    total_tokens += estimate_tokens_from_text(system_prompt)
    
    # Add all message tokens
    for message in agent_messages:
        if isinstance(message, dict):
            # Count role and content
            total_tokens += estimate_tokens_from_text(message.get('role', ''))
            
            content = message.get('content', '')
            if isinstance(content, list):
                # Handle structured content (tool calls, etc.)
                for item in content:
                    if isinstance(item, dict):
                        total_tokens += estimate_tokens_from_text(json.dumps(item))
                    else:
                        total_tokens += estimate_tokens_from_text(str(item))
            else:
                total_tokens += estimate_tokens_from_text(content)
        else:
            # Fallback for non-dict messages
            total_tokens += estimate_tokens_from_text(str(message))
    
    return int(total_tokens)

# Initialize session state for conversation history
if "messages" not in st.session_state:
    st.session_state.messages = []

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

Your comprehensive capabilities include:

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





# Create the Bedrock model
model = BedrockModel(
    model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    max_tokens=64000,
    region_name=region,
    additional_request_fields={
        "thinking": {
            "type": "disabled",
        }
    },
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
        enable_aws_api = os.getenv('ENABLE_AWS_API_SERVER', 'true').lower() == 'true'
        
        # Create billing MCP client
        billing_mcp_client = MCPClient(lambda: stdio_client(
            StdioServerParameters(
                command="python",
                args=["-m", "awslabs.billing_cost_management_mcp_server.server"],
                env=mcp_env
            )
        ))
        
        # AWS API MCP client using pip-installed server
        if enable_aws_api:
            try:
                aws_api_mcp_client = MCPClient(lambda: stdio_client(
                    StdioServerParameters(
                        command="python",
                        args=["-m", "awslabs.aws_api_mcp_server.server"],
                        env=mcp_env
                    )
                ))
                print("✅ AWS API MCP client created")
            except Exception as e:
                print(f"❌ Failed to create AWS API MCP client: {e}")
                aws_api_mcp_client = None
        else:
            print("ℹ️ AWS API MCP server disabled via environment variable")
            aws_api_mcp_client = None
        
        with st.spinner("🔧 Loading FinOps and AWS API tools..."):
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
            
            # Try to start AWS API MCP server (if available)
            if aws_api_mcp_client:
                try:
                    with st.spinner("🔧 Starting AWS API MCP server..."):
                        aws_api_mcp_client.__enter__()
                        st.session_state.aws_api_mcp_client = aws_api_mcp_client
                        aws_api_tools = aws_api_mcp_client.list_tools_sync()
                        all_tools.extend(aws_api_tools)
                        print(f"✅ Loaded {len(aws_api_tools)} tools from AWS API MCP server")
                        st.sidebar.success(f"✅ AWS API Server: {len(aws_api_tools)} tools")
                except Exception as e:
                    print(f"❌ Failed to start AWS API MCP server: {e}")
                    st.sidebar.warning(f"⚠️ AWS API Server Failed: {str(e)}")
                    st.sidebar.info("💡 Continuing with Billing tools only")
            else:
                st.sidebar.info("💡 AWS API Server disabled")
            
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

# Add persistent usage metrics to sidebar
with st.sidebar:
    st.markdown("---")
    st.subheader("💰 Usage & Costs")
    
    if "total_requests" in st.session_state and st.session_state.total_requests > 0:
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Requests", st.session_state.total_requests)
            st.metric("Total Tokens", f"{st.session_state.total_tokens:,}")
        
        with col2:
            st.metric("Total Cost", f"${st.session_state.total_cost:.4f}")
            avg_cost = st.session_state.total_cost / st.session_state.total_requests
            st.metric("Avg Cost/Request", f"${avg_cost:.4f}")
        
        # Cost breakdown
        with st.expander("💡 Cost Details"):
            st.write(f"**Model**: Claude 3.7 Sonnet")
            st.write(f"**Input Rate**: $3.00 per 1M tokens")
            st.write(f"**Output Rate**: $15.00 per 1M tokens")
            
            if st.session_state.total_cost > 0:
                # Simple daily projection based on current session
                requests_per_hour = st.session_state.total_requests  # Rough estimate
                daily_projection = st.session_state.total_cost * 24 / max(1, requests_per_hour)
                monthly_projection = daily_projection * 30
                st.write(f"**Est. Daily**: ~${daily_projection:.3f}")
                st.write(f"**Est. Monthly**: ~${monthly_projection:.2f}")
                
                # Conversation length warning
                if hasattr(st.session_state, 'agent') and st.session_state.agent:
                    conversation_length = len(st.session_state.agent.messages)
                    if conversation_length > 20:
                        st.warning(f"⚠️ Long conversation ({conversation_length} messages) increases costs exponentially!")
                    elif conversation_length > 10:
                        st.info(f"💡 Conversation length: {conversation_length} messages. Consider starting fresh for cost efficiency.")
    else:
        st.info("💡 Usage metrics will appear after your first query")
    
    # Control buttons
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Reset Stats"):
            for key in ["total_tokens", "total_cost", "total_requests"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    
    with col2:
        if st.button("🆕 Fresh Chat"):
            # Clear conversation history to reduce costs
            st.session_state.messages = []
            if hasattr(st.session_state, 'agent') and st.session_state.agent:
                st.session_state.agent.messages = []
            st.session_state.start_index = 0
            st.success("Started fresh conversation!")
            st.rerun()

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.empty()  # This forces the container to render without adding visible content (workaround for streamlit bug)
        st.markdown(clean_markdown_text(message["content"]))

# Chat input
if prompt := st.chat_input("Ask your agent..."):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Clear previous tool usage details
    if "details_placeholder" in st.session_state:
        st.session_state.details_placeholder.empty()
    
    # Display user message
    with st.chat_message("user"):
        st.write(prompt)
    
    # Get response from agent and track usage
    with st.spinner("Thinking..."):
        # Track start time for response time calculation
        import time
        start_time = time.time()
        
        response = st.session_state.agent(prompt)
        
        # Calculate response time
        response_time = time.time() - start_time
    
    # Extract the assistant's response text and usage metrics
    assistant_response = ""
    usage_metrics = None
    
    # Debug: Print the agent messages structure
    print("=== DEBUG: Agent Messages Structure ===")
    for i, m in enumerate(st.session_state.agent.messages[-2:]):  # Last 2 messages
        print(f"Message {i}: {type(m)} - Keys: {list(m.keys()) if isinstance(m, dict) else 'Not a dict'}")
        if isinstance(m, dict):
            print(f"  Role: {m.get('role')}")
            print(f"  Usage: {m.get('usage')}")
            if 'content' in m:
                print(f"  Content type: {type(m['content'])}")
    
    for m in st.session_state.agent.messages:
        if m.get("role") == "assistant" and m.get("content"):
            for content_item in m.get("content", []):
                if "text" in content_item:
                    # We keep only the last response of the assistant
                    assistant_response = content_item["text"]
                    break
        
        # Look for usage information in the message
        if m.get("usage"):
            usage_metrics = m.get("usage")
            print(f"Found usage metrics: {usage_metrics}")
    
    # Also check if the agent itself has usage information
    if hasattr(st.session_state.agent, 'usage'):
        print(f"Agent usage: {st.session_state.agent.usage}")
        usage_metrics = st.session_state.agent.usage
    
    # Check the response object
    if hasattr(response, 'usage'):
        print(f"Response usage: {response.usage}")
        usage_metrics = response.usage
    
    # Calculate token usage and costs
    if usage_metrics:
        input_tokens = usage_metrics.get("inputTokens", 0)
        output_tokens = usage_metrics.get("outputTokens", 0)
        total_tokens = input_tokens + output_tokens
        
        print(f"Usage metrics found - Input: {input_tokens}, Output: {output_tokens}")
        
        # Claude 3.7 Sonnet pricing (as of 2024)
        # Input: $3.00 per 1M tokens, Output: $15.00 per 1M tokens
        input_cost = (input_tokens / 1_000_000) * 3.00
        output_cost = (output_tokens / 1_000_000) * 15.00
        total_cost = input_cost + output_cost
        
        # Update session totals
        if "total_tokens" not in st.session_state:
            st.session_state.total_tokens = 0
            st.session_state.total_cost = 0.0
            st.session_state.total_requests = 0
        
        st.session_state.total_tokens += total_tokens
        st.session_state.total_cost += total_cost
        st.session_state.total_requests += 1
        
        print(f"Updated totals - Requests: {st.session_state.total_requests}, Tokens: {st.session_state.total_tokens}, Cost: ${st.session_state.total_cost:.4f}")
    else:
        print("No usage metrics found - creating IMPROVED estimated metrics based on full conversation")
        
        # IMPROVED: Calculate tokens for the ENTIRE conversation that gets sent to LLM
        # This includes system prompt + all conversation history
        estimated_input_tokens = calculate_conversation_tokens(
            st.session_state.agent.messages, 
            system_prompt
        )
        
        # Output tokens: estimate from assistant response using better method
        estimated_output_tokens = estimate_tokens_from_text(assistant_response)
        estimated_total_tokens = estimated_input_tokens + estimated_output_tokens
        
        # Estimate cost
        estimated_input_cost = (estimated_input_tokens / 1_000_000) * 3.00
        estimated_output_cost = (estimated_output_tokens / 1_000_000) * 15.00
        estimated_total_cost = estimated_input_cost + estimated_output_cost
        
        # Update session totals with estimates
        if "total_tokens" not in st.session_state:
            st.session_state.total_tokens = 0
            st.session_state.total_cost = 0.0
            st.session_state.total_requests = 0
        
        st.session_state.total_tokens += estimated_total_tokens
        st.session_state.total_cost += estimated_total_cost
        st.session_state.total_requests += 1
        
        # Create usage metrics for display
        usage_metrics = {
            "inputTokens": estimated_input_tokens,
            "outputTokens": estimated_output_tokens
        }
        
        print(f"IMPROVED Estimated metrics - Input: {estimated_input_tokens}, Output: {estimated_output_tokens}, Cost: ${estimated_total_cost:.4f}")
        print(f"Conversation length: {len(st.session_state.agent.messages)} messages, System prompt: {estimate_tokens_from_text(system_prompt)} tokens")
        print(f"Updated totals - Requests: {st.session_state.total_requests}, Tokens: {st.session_state.total_tokens}, Cost: ${st.session_state.total_cost:.4f}")
    
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": assistant_response})
    
    # Display assistant response
    with st.chat_message("assistant"):
        
        start_index = st.session_state.start_index      

        # Display last messages from agent, with tool usage detail if any
        st.session_state.details_placeholder = st.empty()  # Create a new placeholder
        with st.session_state.details_placeholder.container():
            for m in st.session_state.agent.messages[start_index:]:
                if m.get("role") == "assistant":
                    for content_item in m.get("content", []):
                        if "text" in content_item:
                            st.write(content_item["text"])
                        elif "toolUse" in content_item:
                            tool_use = content_item["toolUse"]
                            tool_name = tool_use.get("name", "")
                            tool_input = tool_use.get("input", {})
                            st.info(f"Using tool: {tool_name}")
                            st.code(json.dumps(tool_input, indent=2))
            
                elif m.get("role") == "user":
                    for content_item in m.get("content", []):
                        if "toolResult" in content_item:
                            tool_result = content_item["toolResult"]
                            st.info(f"Tool Result: {tool_result.get('status', '')}")
                            for result_content in tool_result.get("content", []):
                                if "text" in result_content:
                                    st.code(result_content["text"])
            
            # Display usage metrics for this request
            if usage_metrics:
                with st.expander("📊 Request Metrics"):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Input Tokens", f"{usage_metrics.get('inputTokens', 0):,}")
                        st.metric("Response Time", f"{response_time:.2f}s")
                    
                    with col2:
                        st.metric("Output Tokens", f"{usage_metrics.get('outputTokens', 0):,}")
                        st.metric("Total Tokens", f"{usage_metrics.get('inputTokens', 0) + usage_metrics.get('outputTokens', 0):,}")
                    
                    with col3:
                        if usage_metrics.get('inputTokens', 0) > 0 or usage_metrics.get('outputTokens', 0) > 0:
                            input_cost = (usage_metrics.get('inputTokens', 0) / 1_000_000) * 3.00
                            output_cost = (usage_metrics.get('outputTokens', 0) / 1_000_000) * 15.00
                            total_request_cost = input_cost + output_cost
                            st.metric("Request Cost", f"${total_request_cost:.4f}")
                            
                            # Cost breakdown
                            st.write(f"Input: ${input_cost:.4f}")
                            st.write(f"Output: ${output_cost:.4f}")

        # Update the number of previous messages
        st.session_state.start_index = len(st.session_state.agent.messages)

# Cleanup function for MCP client (called when session ends)
def cleanup_mcp_clients():
    if "billing_mcp_client" in st.session_state:
        try:
            st.session_state.billing_mcp_client.__exit__(None, None, None)
            print("🧹 Billing MCP client session closed")
        except Exception as e:
            print(f"⚠️ Error closing Billing MCP client: {e}")
    
    if "aws_api_mcp_client" in st.session_state:
        try:
            st.session_state.aws_api_mcp_client.__exit__(None, None, None)
            print("🧹 AWS API MCP client session closed")
        except Exception as e:
            print(f"⚠️ Error closing AWS API MCP client: {e}")

# Register cleanup function
import atexit
atexit.register(cleanup_mcp_clients)


    

