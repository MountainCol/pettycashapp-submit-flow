import boto3
from botocore.exceptions import ClientError
from typing import Optional, Dict
import logging
from datetime import datetime
import uuid

from app.config import get_settings
from app.models.schemas import ReceiptStatus

logger = logging.getLogger(__name__)
settings = get_settings()

class DynamoDBService:
    """Service for DynamoDB operations"""
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb', region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table_name)
    
    def create_receipt_record(self, user_id: str, s3_key: str, file_size: int, 
                             content_type: str, textract_job_id: str) -> str:
        """Create new receipt record in DynamoDB"""
        receipt_id = f"rec_{uuid.uuid4().hex[:16]}"
        timestamp = datetime.utcnow().isoformat()
        
        try:
            self.table.put_item(
                Item={
                    'receipt_id': receipt_id,
                    'user_id': user_id,
                    's3_key': s3_key,
                    'file_size': file_size,
                    'content_type': content_type,
                    'status': ReceiptStatus.PROCESSING.value,
                    'textract_job_id': textract_job_id,
                    'created_at': timestamp,
                    'updated_at': timestamp,
                    'progress': 0
                }
            )
            logger.info(f"Created receipt record: {receipt_id}")
            return receipt_id
        except ClientError as e:
            logger.error(f"Failed to create receipt record: {e}")
            raise
    
    def get_receipt(self, receipt_id: str) -> Optional[Dict]:
        """Get receipt record by ID"""
        try:
            response = self.table.get_item(Key={'receipt_id': receipt_id})
            return response.get('Item')
        except ClientError as e:
            logger.error(f"Failed to get receipt: {e}")
            return None
    
    def update_receipt_status(self, receipt_id: str, status: str, 
                             extracted_data: Optional[Dict] = None,
                             error: Optional[Dict] = None,
                             progress: Optional[int] = None):
        """Update receipt status and data"""
        timestamp = datetime.utcnow().isoformat()
        
        update_expr = "SET #status = :status, updated_at = :updated_at"
        expr_attr_names = {'#status': 'status'}
        expr_attr_values = {
            ':status': status,
            ':updated_at': timestamp
        }
        
        if extracted_data:
            update_expr += ", extracted_data = :extracted_data"
            expr_attr_values[':extracted_data'] = extracted_data
        
        if error:
            update_expr += ", error = :error"
            expr_attr_values[':error'] = error
        
        if progress is not None:
            update_expr += ", progress = :progress"
            expr_attr_values[':progress'] = progress
        
        if status == ReceiptStatus.COMPLETED.value:
            update_expr += ", completed_at = :completed_at"
            expr_attr_values[':completed_at'] = timestamp
        
        try:
            self.table.update_item(
                Key={'receipt_id': receipt_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values
            )
            logger.info(f"Updated receipt {receipt_id} status to {status}")
        except ClientError as e:
            logger.error(f"Failed to update receipt status: {e}")
            raise
