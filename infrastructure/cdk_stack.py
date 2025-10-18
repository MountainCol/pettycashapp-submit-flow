from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_sns as sns,
    aws_cognito as cognito,
    aws_iam as iam,
    Duration,
    RemovalPolicy
)
from constructs import Construct

class PettyCashStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 Bucket for receipts
        receipts_bucket = s3.Bucket(
            self, "ReceiptsBucket",
            bucket_name="pettycash-receipts",
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.PUT, s3.HttpMethods.POST],
                    allowed_origins=["*"],
                    allowed_headers=["*"]
                )
            ],
            removal_policy=RemovalPolicy.RETAIN
        )

        # DynamoDB Table
        receipts_table = dynamodb.Table(
            self, "ReceiptsTable",
            table_name="pettycash-receipts",
            partition_key=dynamodb.Attribute(
                name="receipt_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN
        )

        # Add GSI for user queries
        receipts_table.add_global_secondary_index(
            index_name="user_id-created_at-index",
            partition_key=dynamodb.Attribute(
                name="user_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING
            )
        )

        # SNS Topic for notifications
        notifications_topic = sns.Topic(
            self, "NotificationsTopic",
            topic_name="pettycash-notifications"
        )

        # Cognito User Pool
        user_pool = cognito.UserPool(
            self, "UserPool",
            user_pool_name="pettycash-users",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True)
        )

        user_pool_client = user_pool.add_client(
            "AppClient",
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True
            )
        )

        # Lambda Function
        api_lambda = lambda_.Function(
            self, "ApiLambda",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="app.main.handler",
            code=lambda_.Code.from_asset("../backend"),
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "S3_BUCKET_NAME": receipts_bucket.bucket_name,
                "DYNAMODB_TABLE_NAME": receipts_table.table_name,
                "SNS_TOPIC_ARN": notifications_topic.topic_arn,
                "COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "COGNITO_APP_CLIENT_ID": user_pool_client.user_pool_client_id
            }
        )

        # Grant permissions
        receipts_bucket.grant_read_write(api_lambda)
        receipts_table.grant_read_write_data(api_lambda)
        notifications_topic.grant_publish(api_lambda)
        
        # Grant Textract permissions
        api_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "textract:StartExpenseAnalysis",
                    "textract:GetExpenseAnalysis"
                ],
                resources=["*"]
            )
        )

        # API Gateway
        api = apigw.LambdaRestApi(
            self, "PettyCashApi",
            handler=api_lambda,
            proxy=True,
            rest_api_name="PettyCash API"
        )
