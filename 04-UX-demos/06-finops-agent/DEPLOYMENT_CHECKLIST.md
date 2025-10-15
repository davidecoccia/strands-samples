# FinOps AI Assistant - Deployment Checklist

## ✅ Pre-Deployment Requirements

### 1. AWS Prerequisites
- [ ] AWS CLI installed and configured
- [ ] AWS CDK installed (`npm install -g aws-cdk`)
- [ ] Python 3.8+ installed
- [ ] Docker installed
- [ ] Chrome browser for testing

### 2. AWS Account Setup
- [ ] `anthropic.claude-3-7-sonnet-20250219-v1:0` model activated in Amazon Bedrock
- [ ] Sufficient permissions to create IAM roles, VPC, ECS, ALB, CloudFront, Cognito
- [ ] Cost Explorer enabled (for billing MCP server functionality)
- [ ] Compute Optimizer enabled (for rightsizing recommendations)

### 3. Configuration Updates
- [ ] Update `docker_app/config_file.py`:
  - [ ] Set unique `STACK_NAME` (default: "FinOps-AI-Chatbot")
  - [ ] Set unique `CUSTOM_HEADER_VALUE` 
  - [ ] Set unique `SECRETS_MANAGER_ID`
  - [ ] Set correct `DEPLOYMENT_REGION`
  - [ ] Keep `ENABLE_AUTH = False` for initial deployment

## 🚀 Deployment Steps

### 1. Install Dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Bootstrap CDK (first time only)
```bash
cdk bootstrap
```

### 3. Deploy the Stack

**Same-account deployment (uses container role permissions directly):**
```bash
cdk deploy
```

**Cross-account deployment (assumes role in management account):**
```bash
cdk deploy -c targetRoleArn=arn:aws:iam::MGMT-ACCOUNT-ID:role/FinOpsChatbotCrossAccountRole
```

**Expected time**: 5-10 minutes

### 4. Note the Outputs
After deployment, save these values:
- [ ] CloudFront Distribution URL
- [ ] Cognito User Pool ID
- [ ] Cross-account configuration (if applicable)
- [ ] ECS Task Role ARN (needed for management account trust policy)

### 5. Create Cognito User (if authentication enabled)
- [ ] Go to AWS Console → Cognito → User Pools
- [ ] Find your user pool (from step 4)
- [ ] Create a new user with username/password
- [ ] Set temporary password and force password change on first login

### 6. Enable Authentication (Optional)
- [ ] Update `docker_app/config_file.py`: Set `ENABLE_AUTH = True`
- [ ] Redeploy: `cdk deploy`

## 🧪 Testing

### 1. Access the Application
- [ ] Open the CloudFront Distribution URL in Chrome
- [ ] If auth enabled: Login with Cognito credentials
- [ ] If auth disabled: Direct access to app

### 2. Test FinOps Functionality
- [ ] Try sample queries from the app's expander
- [ ] Verify MCP servers load successfully (check sidebar)
- [ ] Test cost analysis queries
- [ ] Test AWS service investigation queries

### 3. Monitor Usage
- [ ] Check usage metrics in sidebar
- [ ] Verify cost tracking is working
- [ ] Test reset functionality

## 🔧 Local Development

### 1. Setup Local Environment
```bash
cd docker_app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Locally
```bash
# Regular version
streamlit run app.py --server.port 8080

# Streaming version
streamlit run app_streaming.py --server.port 8080
```

### 3. Access Local App
- [ ] Open `http://localhost:8080/`
- [ ] Authentication is disabled by default for local development

## 🛡️ Security Considerations

### Production Recommendations
- [ ] Enable authentication (`ENABLE_AUTH = True`)
- [ ] Configure HTTPS with your own domain and SSL certificate
- [ ] Review and restrict IAM permissions as needed
- [ ] Enable CloudTrail for audit logging
- [ ] Consider AWS WAF for additional protection
- [ ] Enable GuardDuty for threat detection
- [ ] Regular security reviews and updates

### Network Security
- [ ] Review VPC configuration
- [ ] Consider private subnets for ECS tasks
- [ ] Implement network ACLs if needed
- [ ] Review security group rules

## 🔍 Troubleshooting

### Common Issues
1. **MCP Server Fails to Start**
   - Check AWS credentials are properly configured
   - Verify IAM permissions include all required services
   - Check CloudWatch logs for detailed error messages

2. **Bedrock Access Denied**
   - Ensure Claude 3.7 Sonnet model is activated
   - Verify IAM role has Bedrock permissions
   - Check region configuration

3. **Cost Explorer Errors**
   - Ensure Cost Explorer is enabled in AWS account
   - Verify billing permissions in IAM policy
   - Some cost data may take 24-48 hours to appear

4. **Authentication Issues**
   - Verify Cognito user pool configuration
   - Check user credentials and status
   - Ensure secrets manager permissions

### Logs and Monitoring
- [ ] Check ECS task logs in CloudWatch
- [ ] Monitor ALB access logs
- [ ] Review CloudFront logs if needed
- [ ] Check application logs for MCP server status

## 📊 Cost Optimization

### Expected Costs (Approximate)
- **ECS Fargate**: ~$15-30/month (0.25 vCPU, 0.5GB RAM)
- **ALB**: ~$20/month + data processing
- **CloudFront**: ~$1-5/month (depending on usage)
- **Cognito**: Free tier covers most use cases
- **Bedrock**: Pay per token usage (~$3-15 per 1M input tokens)

### Cost Monitoring
- [ ] Set up AWS Budgets for the stack
- [ ] Monitor Bedrock usage and costs
- [ ] Use the app's built-in usage tracking
- [ ] Consider auto-scaling policies for production

## 🏢 Cross-Account Setup (Optional)

If deploying to a member account but need access to management account billing data:

### 1. Management Account Role Setup
Create an IAM role in the management account with:

**Role Name**: `FinOpsChatbotCrossAccountRole`

**Permissions Policy** (attach the same FinOps permissions from the CDK stack):
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ce:GetCostAndUsage",
                "ce:GetUsageReport",
                "ce:GetReservationCoverage",
                "ce:GetReservationPurchaseRecommendation",
                "ce:GetReservationUtilization",
                "ce:GetSavingsPlansUtilization",
                "ce:GetSavingsPlansCoverage",
                "ce:GetDimensionValues",
                "ce:GetCostCategories",
                "ce:GetAnomalies",
                "budgets:ViewBudget",
                "budgets:DescribeBudgets",
                "budgets:DescribeBudgetPerformanceHistory",
                "compute-optimizer:GetRecommendationSummaries",
                "compute-optimizer:GetEC2InstanceRecommendations",
                "compute-optimizer:GetEBSVolumeRecommendations",
                "compute-optimizer:GetLambdaFunctionRecommendations",
                "compute-optimizer:GetAutoScalingGroupRecommendations",
                "freetier:GetFreeTierUsage"
            ],
            "Resource": "*"
        }
    ]
}
```

**Trust Policy** (replace with actual ECS task role ARN from CDK output):
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "AWS": "arn:aws:iam::MEMBER-ACCOUNT-ID:role/FinOps-AI-Chatbot-WebappTaskDefTaskRole-XXXXX"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
```

### 2. Deploy with Cross-Account Role
```bash
cdk deploy -c targetRoleArn=arn:aws:iam::123456789012:role/FinOpsChatbotCrossAccountRole
```

## 🔄 Updates and Maintenance

### Regular Tasks
- [ ] Update dependencies regularly
- [ ] Monitor security advisories
- [ ] Review and rotate secrets
- [ ] Update Bedrock model versions as available
- [ ] Monitor and optimize costs

### Updating the Application
1. Make changes to code
2. Test locally
3. Deploy with `cdk deploy`
4. Monitor deployment and test functionality

## 📞 Support Resources

- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [MCP Documentation](https://modelcontextprotocol.io/)
- [AWS Cost Explorer Documentation](https://docs.aws.amazon.com/cost-management/)