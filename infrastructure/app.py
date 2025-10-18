#!/usr/bin/env python3
import os
import aws_cdk as cdk
from cdk_stack import PettyCashStack

app = cdk.App()

# Automatically detect account and region from environment
PettyCashStack(app, "PettyCashStack",
    env=cdk.Environment(
        account=os.environ.get('CDK_DEFAULT_ACCOUNT'),
        region=os.environ.get('CDK_DEFAULT_REGION', 'eu-west-1')
    )
)

app.synth()
