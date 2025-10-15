from aws_cdk import (
    # Duration,
    Stack,
    Tags,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_cognito as cognito,
    aws_secretsmanager as secretsmanager,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_elasticloadbalancingv2 as elbv2,
    SecretValue,
    CfnOutput,
)
from constructs import Construct
from docker_app.config_file import Config

CUSTOM_HEADER_NAME = "X-Custom-Header"

class CdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Add global tags to all resources in this stack
        Tags.of(self).add("auto-delete", "no")

        # Define prefix that will be used in some resource names
        prefix = Config.STACK_NAME

        # Create Cognito user pool (keep existing configuration to avoid update conflicts)
        user_pool = cognito.UserPool(self, f"{prefix}UserPool")

        # Optional Custom Domain for better UX
        user_pool_domain = None
        if Config.COGNITO_CUSTOM_DOMAIN:
            user_pool_domain = cognito.UserPoolDomain(
                self, f"{prefix}UserPoolDomain",
                user_pool=user_pool,
                cognito_domain=cognito.CognitoDomainOptions(
                    domain_prefix=Config.COGNITO_CUSTOM_DOMAIN
                )
            )

        # VPC for ALB and ECS cluster
        vpc = ec2.Vpc(
            self,
            f"{prefix}AppVpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            vpc_name=f"{prefix}-stl-vpc",
            nat_gateways=1,
        )

        ecs_security_group = ec2.SecurityGroup(
            self,
            f"{prefix}SecurityGroupECS",
            vpc=vpc,
            security_group_name=f"{prefix}-stl-ecs-sg",
        )

        alb_security_group = ec2.SecurityGroup(
            self,
            f"{prefix}SecurityGroupALB",
            vpc=vpc,
            security_group_name=f"{prefix}-stl-alb-sg",
        )

        ecs_security_group.add_ingress_rule(
            peer=alb_security_group,
            connection=ec2.Port.tcp(8501),
            description="ALB traffic",
        )

        # ECS cluster and service definition
        cluster = ecs.Cluster(
            self,
            f"{prefix}Cluster",
            enable_fargate_capacity_providers=True,
            vpc=vpc)

        # ALB to connect to ECS
        alb = elbv2.ApplicationLoadBalancer(
            self,
            f"{prefix}Alb",
            vpc=vpc,
            internet_facing=True,
            load_balancer_name=f"{prefix}-stl",
            security_group=alb_security_group,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        fargate_task_definition = ecs.FargateTaskDefinition(
            self,
            f"{prefix}WebappTaskDef",
            memory_limit_mib=2048,
            cpu=1024,
        )

        # Build Dockerfile from local folder and push to ECR
        image = ecs.ContainerImage.from_asset(
            'docker_app',
            build_args={
                'BUILDKIT_INLINE_CACHE': '1'
            }
        )

        # Get TARGET_ROLE_ARN from CDK context for cross-account access
        target_role_arn = self.node.try_get_context("targetRoleArn")
        
        # Set up container environment variables
        container_environment = {
            "AWS_DEFAULT_REGION": Config.DEPLOYMENT_REGION,
            "BEDROCK_MODEL_ID": Config.DEFAULT_BEDROCK_MODEL,  # Configurable model
        }
        
        # Add TARGET_ROLE_ARN if provided via CDK context
        if target_role_arn:
            container_environment["TARGET_ROLE_ARN"] = target_role_arn

        fargate_task_definition.add_container(
            f"{prefix}WebContainer",
            # Use an image from DockerHub
            image=image,
            environment=container_environment,
            port_mappings=[
                ecs.PortMapping(
                    container_port=8501,
                    protocol=ecs.Protocol.TCP)],
            logging=ecs.LogDrivers.aws_logs(stream_prefix="WebContainerLogs"),
        )

        service = ecs.FargateService(
            self,
            f"{prefix}ECSService",
            cluster=cluster,
            task_definition=fargate_task_definition,
            service_name=f"{prefix}-stl-front",
            security_groups=[ecs_security_group],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # Grant access to Bedrock
        bedrock_policy = iam.Policy(self, f"{prefix}BedrockPolicy",
                                    statements=[
                                        iam.PolicyStatement(
                                            actions=["bedrock:InvokeModelWithResponseStream"],
                                            resources=["*"]
                                        )
                                    ]
                                    )
        
        # Grant access to AWS services for FinOps functionality
        finops_policy = iam.Policy(self, f"{prefix}FinOpsPolicy",
                                   statements=[
                                       # Cost Explorer and Billing
                                       iam.PolicyStatement(
                                           actions=[
                                               "ce:GetCostAndUsage",
                                               "ce:GetUsageReport",
                                               "ce:GetReservationCoverage",
                                               "ce:GetReservationPurchaseRecommendation",
                                               "ce:GetReservationUtilization",
                                               "ce:GetSavingsPlansUtilization",
                                               "ce:GetSavingsPlansUtilizationDetails",
                                               "ce:GetSavingsPlansCoverage",
                                               "ce:GetSavingsPlansUtilizationDetails",
                                               "ce:GetDimensionValues",
                                               "ce:GetReservationUtilization",
                                               "ce:GetCostCategories",
                                               "ce:GetUsageReport",
                                               "ce:GetAnomalies",
                                               "ce:GetAnomalyDetectors",
                                               "ce:GetAnomalyMonitors",
                                               "ce:GetAnomalySubscriptions"
                                           ],
                                           resources=["*"]
                                       ),
                                       # Budgets
                                       iam.PolicyStatement(
                                           actions=[
                                               "budgets:ViewBudget",
                                               "budgets:DescribeBudgets",
                                               "budgets:DescribeBudgetPerformanceHistory"
                                           ],
                                           resources=["*"]
                                       ),
                                       # Compute Optimizer
                                       iam.PolicyStatement(
                                           actions=[
                                               "compute-optimizer:GetRecommendationSummaries",
                                               "compute-optimizer:GetEC2InstanceRecommendations",
                                               "compute-optimizer:GetEC2RecommendationProjectedMetrics",
                                               "compute-optimizer:GetEBSVolumeRecommendations",
                                               "compute-optimizer:GetLambdaFunctionRecommendations",
                                               "compute-optimizer:GetAutoScalingGroupRecommendations",
                                               "compute-optimizer:GetEnrollmentStatus"
                                           ],
                                           resources=["*"]
                                       ),
                                       # Free Tier
                                       iam.PolicyStatement(
                                           actions=[
                                               "freetier:GetFreeTierUsage"
                                           ],
                                           resources=["*"]
                                       ),
                                       # AWS Services for investigation
                                       iam.PolicyStatement(
                                           actions=[
                                               "ec2:Describe*",
                                               "rds:Describe*",
                                               "s3:ListAllMyBuckets",
                                               "s3:GetBucketLocation",
                                               "s3:GetBucketTagging",
                                               "s3:GetBucketVersioning",
                                               "s3:GetBucketPolicy",
                                               "s3:GetBucketAcl",
                                               "s3:GetBucketCors",
                                               "s3:GetBucketWebsite",
                                               "s3:GetBucketLogging",
                                               "s3:GetBucketNotification",
                                               "s3:GetBucketRequestPayment",
                                               "s3:GetBucketVersioning",
                                               "lambda:List*",
                                               "lambda:Get*",
                                               "iam:List*",
                                               "iam:Get*",
                                               "cloudformation:Describe*",
                                               "cloudformation:List*",
                                               "cloudwatch:Describe*",
                                               "cloudwatch:Get*",
                                               "cloudwatch:List*",
                                               "logs:Describe*",
                                               "autoscaling:Describe*",
                                               "elasticloadbalancing:Describe*",
                                               "route53:List*",
                                               "route53:Get*"
                                           ],
                                           resources=["*"]
                                       ),
                                       # S3 Storage Lens
                                       iam.PolicyStatement(
                                           actions=[
                                               "s3:GetStorageLensConfiguration",
                                               "s3:ListStorageLensConfigurations",
                                               "s3:GetStorageLensConfigurationTagging"
                                           ],
                                           resources=["*"]
                                       )
                                   ]
                                   )
        
        task_role = fargate_task_definition.task_role
        task_role.attach_inline_policy(bedrock_policy)
        task_role.attach_inline_policy(finops_policy)
        
        # Add STS assume role permission if TARGET_ROLE_ARN is provided
        if target_role_arn:
            assume_role_policy = iam.Policy(self, f"{prefix}AssumeRolePolicy",
                                          statements=[
                                              iam.PolicyStatement(
                                                  actions=["sts:AssumeRole"],
                                                  resources=[target_role_arn]
                                              )
                                          ]
                                          )
            task_role.attach_inline_policy(assume_role_policy)

        # Add ALB as CloudFront Origin
        origin = origins.LoadBalancerV2Origin(
            alb,
            custom_headers={CUSTOM_HEADER_NAME: Config.CUSTOM_HEADER_VALUE},
            origin_shield_enabled=False,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
        )

        cloudfront_distribution = cloudfront.Distribution(
            self,
            f"{prefix}CfDist",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
            ),
        )

        # Now create the Cognito User Pool Client with proper callback URLs
        # Determine callback URLs
        callback_urls = [
            f"https://{cloudfront_distribution.domain_name}/",
            "http://localhost:8080/",  # For local development
        ]
        
        # Add custom domain callback if configured
        if user_pool_domain:
            callback_urls.append(f"https://{Config.COGNITO_CUSTOM_DOMAIN}.auth.{Config.DEPLOYMENT_REGION}.amazoncognito.com/oauth2/idpresponse")

        # Add SAML Identity Provider (if enabled and metadata URL is provided)
        saml_provider = None
        supported_identity_providers = [cognito.UserPoolClientIdentityProvider.COGNITO]
        
        if Config.ENABLE_SAML_FEDERATION and Config.SAML_METADATA_URL:
            saml_provider = cognito.UserPoolIdentityProviderSaml(
                self, f"{prefix}SAMLProvider",
                user_pool=user_pool,
                name=Config.SAML_PROVIDER_NAME,
                metadata=cognito.UserPoolIdentityProviderSamlMetadata.url(
                    Config.SAML_METADATA_URL
                ),
                # Map SAML attributes to Cognito attributes
                attribute_mapping=cognito.AttributeMapping(
                    email=cognito.ProviderAttribute.other("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"),
                    given_name=cognito.ProviderAttribute.other("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname"),
                    family_name=cognito.ProviderAttribute.other("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname"),
                ),
            )
            supported_identity_providers.append(cognito.UserPoolClientIdentityProvider.custom(Config.SAML_PROVIDER_NAME))

        # Enhanced Cognito client for SAML
        user_pool_client = cognito.UserPoolClient(
            self, f"{prefix}UserPoolClient",
            user_pool=user_pool,
            generate_secret=True,
            # Enhanced settings for SAML federation
            supported_identity_providers=supported_identity_providers,
            
            # OAuth settings for hosted UI
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                ),
                scopes=[
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.PROFILE,
                ],
                callback_urls=callback_urls,
                logout_urls=callback_urls,
            ),
        )

        # Store Cognito parameters in a Secrets Manager secret (enhanced for SAML)
        secret_data = {
            "pool_id": SecretValue.unsafe_plain_text(user_pool.user_pool_id),
            "app_client_id": SecretValue.unsafe_plain_text(user_pool_client.user_pool_client_id),
            "app_client_secret": user_pool_client.user_pool_client_secret,
            "region": SecretValue.unsafe_plain_text(Config.DEPLOYMENT_REGION),
            "saml_enabled": SecretValue.unsafe_plain_text(str(Config.ENABLE_SAML_FEDERATION)),
            "saml_provider_name": SecretValue.unsafe_plain_text(Config.SAML_PROVIDER_NAME),
        }
        
        # Add domain information if custom domain is configured
        if user_pool_domain:
            secret_data["domain"] = SecretValue.unsafe_plain_text(
                f"{Config.COGNITO_CUSTOM_DOMAIN}.auth.{Config.DEPLOYMENT_REGION}.amazoncognito.com"
            )
        else:
            secret_data["domain"] = SecretValue.unsafe_plain_text(
                f"{user_pool.user_pool_id}.auth.{Config.DEPLOYMENT_REGION}.amazoncognito.com"
            )

        secret = secretsmanager.Secret(
            self, f"{prefix}ParamCognitoSecret",
            secret_object_value=secret_data,
            secret_name=Config.SECRETS_MANAGER_ID
        )

        # Grant access to read the secret in Secrets Manager
        secret.grant_read(task_role)

        # ALB Listener
        http_listener = alb.add_listener(
            f"{prefix}HttpListener",
            port=80,
            open=True,
        )

        http_listener.add_targets(
            f"{prefix}TargetGroup",
            target_group_name=f"{prefix}-tg",
            port=8501,
            priority=1,
            conditions=[
                elbv2.ListenerCondition.http_header(
                    CUSTOM_HEADER_NAME,
                    [Config.CUSTOM_HEADER_VALUE])],
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[service],
        )
        # add a default action to the listener that will deny all requests that
        # do not have the custom header
        http_listener.add_action(
            "default-action",
            action=elbv2.ListenerAction.fixed_response(
                status_code=403,
                content_type="text/plain",
                message_body="Access denied",
            ),
        )

        # Output CloudFront URL
        CfnOutput(self, "CloudFrontDistributionURL",
                  value=cloudfront_distribution.domain_name)
        # Output Cognito pool id
        CfnOutput(self, "CognitoPoolId",
                  value=user_pool.user_pool_id)
        
        # Output cross-account configuration
        if target_role_arn:
            CfnOutput(self, "CrossAccountRoleArn",
                      value=target_role_arn,
                      description="Management account role that will be assumed")
            CfnOutput(self, "TaskRoleArn",
                      value=task_role.role_arn,
                      description="ECS task role - add this to management account role trust policy")
        else:
            CfnOutput(self, "DeploymentMode",
                      value="Same-account deployment (no cross-account role configured)",
                      description="To enable cross-account access, redeploy with -c targetRoleArn=<role-arn>")

        # SAML Configuration Outputs (for Identity Center setup)
        if Config.ENABLE_SAML_FEDERATION:
            CfnOutput(self, "SAMLConfigurationInstructions",
                      value="Configure SAML app in Identity Center (eu-central-1) with these details:",
                      description="SAML Setup Instructions")
            
            CfnOutput(self, "SAMLEntityId", 
                      value=f"urn:amazon:cognito:sp:{user_pool.user_pool_id}",
                      description="Use this as Entity ID in Identity Center")
            
            CfnOutput(self, "SAMLACSUrl",
                      value=f"https://cognito-idp.{Config.DEPLOYMENT_REGION}.amazonaws.com/{user_pool.user_pool_id}/saml2/idpresponse",
                      description="Use this as ACS URL in Identity Center")
            
            if user_pool_domain:
                CfnOutput(self, "CognitoHostedUIUrl",
                          value=f"https://{Config.COGNITO_CUSTOM_DOMAIN}.auth.{Config.DEPLOYMENT_REGION}.amazoncognito.com/login?client_id={user_pool_client.user_pool_client_id}&response_type=code&scope=email+openid+profile&redirect_uri=https://{cloudfront_distribution.domain_name}/",
                          description="Cognito Hosted UI URL for testing")
            
            CfnOutput(self, "NextSteps",
                      value="1. Create SAML app in Identity Center, 2. Get metadata URL, 3. Update SAML_METADATA_URL in config, 4. Redeploy",
                      description="Next steps to complete SAML setup")
