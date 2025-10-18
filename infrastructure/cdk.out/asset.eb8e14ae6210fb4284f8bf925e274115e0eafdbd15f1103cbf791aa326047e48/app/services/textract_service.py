import boto3
from botocore.exceptions import ClientError
from typing import Dict, Optional
import logging
from decimal import Decimal
import re

from app.config import get_settings
from app.models.schemas import ExtractedData, ConfidenceScores

logger = logging.getLogger(__name__)
settings = get_settings()

class TextractService:
    """Service for AWS Textract OCR operations"""
    
    def __init__(self):
        self.textract_client = boto3.client('textract', region_name=settings.aws_region)
        self.bucket_name = settings.s3_bucket_name
    
    def start_expense_analysis(self, s3_key: str) -> str:
        """Start asynchronous expense analysis job"""
        try:
            response = self.textract_client.start_expense_analysis(
                DocumentLocation={
                    'S3Object': {
                        'Bucket': self.bucket_name,
                        'Name': s3_key
                    }
                }
            )
            job_id = response['JobId']
            logger.info(f"Started Textract job {job_id} for {s3_key}")
            return job_id
        except ClientError as e:
            logger.error(f"Failed to start Textract job: {e}")
            raise
    
    def get_expense_analysis(self, job_id: str) -> Dict:
        """Get results of expense analysis job"""
        try:
            response = self.textract_client.get_expense_analysis(
                JobId=job_id
            )
            return response
        except ClientError as e:
            logger.error(f"Failed to get Textract results: {e}")
            raise
    
    def check_job_status(self, job_id: str) -> str:
        """Check status of Textract job"""
        try:
            response = self.textract_client.get_expense_analysis(JobId=job_id)
            return response['JobStatus']  # IN_PROGRESS, SUCCEEDED, FAILED
        except ClientError as e:
            logger.error(f"Failed to check job status: {e}")
            raise
    
    def parse_expense_data(self, textract_response: Dict) -> Optional[ExtractedData]:
        """Parse Textract response into structured expense data"""
        try:
            expense_documents = textract_response.get('ExpenseDocuments', [])
            
            if not expense_documents:
                return None
            
            doc = expense_documents[0]
            summary_fields = doc.get('SummaryFields', [])
            
            merchant = None
            amount = None
            date = None
            tax = None
            currency = "USD"
            
            confidence_scores = {
                'merchant': 0.0,
                'amount': 0.0,
                'date': 0.0
            }
            
            for field in summary_fields:
                field_type = field.get('Type', {}).get('Text', '').upper()
                value = field.get('ValueDetection', {}).get('Text', '')
                confidence = field.get('ValueDetection', {}).get('Confidence', 0) / 100
                
                if 'VENDOR' in field_type or 'MERCHANT' in field_type:
                    merchant = value
                    confidence_scores['merchant'] = confidence
                
                elif 'TOTAL' in field_type and 'AMOUNT' in field_type:
                    amount_str = re.sub(r'[^0-9.]', '', value)
                    if amount_str:
                        amount = Decimal(amount_str)
                        confidence_scores['amount'] = confidence
                
                elif 'TAX' in field_type:
                    tax_str = re.sub(r'[^0-9.]', '', value)
                    if tax_str:
                        tax = Decimal(tax_str)
                
                elif 'DATE' in field_type:
                    date = self._parse_date(value)
                    confidence_scores['date'] = confidence
            
            return ExtractedData(
                merchant=merchant,
                amount=amount,
                currency=currency,
                date=date,
                tax=tax,
                confidence_scores=ConfidenceScores(**confidence_scores)
            )
            
        except Exception as e:
            logger.error(f"Failed to parse Textract data: {e}")
            return None
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string to YYYY-MM-DD format"""
        from datetime import datetime
        
        formats = [
            '%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d',
            '%m-%d-%Y', '%d-%m-%Y', '%B %d, %Y',
            '%b %d, %Y', '%d %B %Y', '%d %b %Y'
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        return None
