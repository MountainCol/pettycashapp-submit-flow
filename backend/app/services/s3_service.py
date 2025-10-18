import boto3
from botocore.exceptions import ClientError
from typing import Optional
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class S3Service:
    """Service for S3 operations"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3', region_name=settings.aws_region)
        self.bucket_name = settings.s3_bucket_name
    
    def verify_object_exists(self, s3_key: str) -> bool:
        """Check if S3 object exists"""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise
    
    def get_object_metadata(self, s3_key: str) -> Optional[dict]:
        """Get S3 object metadata"""
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            return {
                'content_type': response.get('ContentType'),
                'content_length': response.get('ContentLength'),
                'last_modified': response.get('LastModified'),
                'metadata': response.get('Metadata', {})
            }
        except ClientError as e:
            logger.error(f"Failed to get object metadata: {e}")
            return None
    
    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> str:
        """Generate presigned URL for S3 object"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise
    
    def validate_user_owns_object(self, s3_key: str, user_id: str) -> bool:
        """Validate that S3 key belongs to user"""
        # Expected format: receipts/company_123/user_456/filename.jpg
        parts = s3_key.split('/')
        if len(parts) >= 3:
            key_user_id = parts[2].replace('user_', '')
            return key_user_id == user_id
        return False
