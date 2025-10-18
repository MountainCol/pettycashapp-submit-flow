import boto3
from botocore.exceptions import ClientError
import logging
import json
from typing import Dict

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class SNSService:
    """Service for SNS notifications"""
    
    def __init__(self):
        self.sns_client = boto3.client('sns', region_name=settings.aws_region)
        self.topic_arn = settings.sns_topic_arn
    
    def send_success_notification(self, user_email: str, receipt_id: str, 
                                  merchant: str, amount: str):
        """Send success notification to user"""
        message = {
            'notification_type': 'receipt_success',
            'receipt_id': receipt_id,
            'status': 'success',
            'title': 'Receipt Upload Successful! ✅',
            'message': f'Your receipt from {merchant} for ${amount} has been successfully processed.',
            'action': 'create_expense',
            'user_email': user_email
        }
        
        self._publish_notification(message, user_email)
    
    def send_failure_notification(self, user_email: str, receipt_id: str, 
                                 error_message: str):
        """Send failure notification to user"""
        message = {
            'notification_type': 'receipt_failure',
            'receipt_id': receipt_id,
            'status': 'failed',
            'title': 'Receipt Upload Failed ❌',
            'message': f'We couldn\'t process your receipt. {error_message}',
            'action': 'upload_again',
            'user_email': user_email
        }
        
        self._publish_notification(message, user_email)
    
    def _publish_notification(self, message: Dict, user_email: str):
        """Publish notification to SNS topic"""
        try:
            response = self.sns_client.publish(
                TopicArn=self.topic_arn,
                Message=json.dumps(message),
                Subject=message['title'],
                MessageAttributes={
                    'user_email': {
                        'DataType': 'String',
                        'StringValue': user_email
                    },
                    'notification_type': {
                        'DataType': 'String',
                        'StringValue': message['notification_type']
                    }
                }
            )
            logger.info(f"Sent notification to {user_email}: {message['title']}")
            return response
        except ClientError as e:
            logger.error(f"Failed to send SNS notification: {e}")
            raise
