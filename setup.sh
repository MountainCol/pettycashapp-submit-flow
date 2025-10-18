#!/bin/bash

# PettyCash Receipt Upload Flow - Complete Setup Script
# This creates all necessary files for S3 upload → Textract OCR → SNS notifications

echo "🚀 Setting up PettyCash Receipt Upload Flow..."

# ============================================================================
# BACKEND - Requirements
# ============================================================================

cat > backend/requirements.txt << 'EOF'
fastapi==0.109.0
uvicorn==0.27.0
mangum==0.17.0
boto3==1.34.34
pydantic==2.5.3
pydantic-settings==2.1.0
python-jose[cryptography]==3.3.0
python-multipart==0.0.6
AWS-Lambda-Powertools==2.31.0
pytest==7.4.4
pytest-asyncio==0.23.3
moto==5.0.0
httpx==0.26.0
EOF

# ============================================================================
# BACKEND - App Init
# ============================================================================

cat > backend/app/__init__.py << 'EOF'
"""PettyCash API Application"""
__version__ = "1.0.0"
EOF

# ============================================================================
# BACKEND - Main Application
# ============================================================================

cat > backend/app/main.py << 'EOF'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from datetime import datetime

from app.routers import receipts, expenses
from app.models.schemas import HealthResponse

app = FastAPI(
    title="PettyCash API",
    description="Receipt upload and expense management API",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(receipts.router, prefix="/v1/expenses/receipts", tags=["receipts"])
app.include_router(expenses.router, prefix="/v1/expenses", tags=["expenses"])

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.get("/")
async def root():
    return {
        "message": "PettyCash API",
        "version": "1.0.0",
        "docs": "/docs"
    }

# Lambda handler
handler = Mangum(app)
EOF

# ============================================================================
# BACKEND - Configuration
# ============================================================================

cat > backend/app/config.py << 'EOF'
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """Application settings"""
    
    # AWS Configuration
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "pettycash-receipts"
    dynamodb_table_name: str = "pettycash-receipts"
    sns_topic_arn: str = ""
    
    # Cognito Configuration
    cognito_user_pool_id: str = ""
    cognito_region: str = "us-east-1"
    cognito_app_client_id: str = ""
    
    # API Configuration
    api_version: str = "v1"
    max_file_size: int = 10485760  # 10MB
    allowed_file_types: list = ["image/jpeg", "image/png", "image/jpg", "application/pdf"]
    
    # OCR Configuration
    textract_timeout: int = 60
    min_confidence_score: float = 0.8
    
    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    return Settings()
EOF

# ============================================================================
# BACKEND - Models Init
# ============================================================================

touch backend/app/models/__init__.py

# ============================================================================
# BACKEND - Schemas
# ============================================================================

cat > backend/app/models/schemas.py << 'EOF'
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, List
from datetime import datetime
from decimal import Decimal
from enum import Enum

class ReceiptStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ExpenseStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"

class PaymentMethod(str, Enum):
    PERSONAL_CARD = "personal_card"
    CASH = "cash"
    COMPANY_CARD = "company_card"

class ExpenseCategory(str, Enum):
    MEALS = "meals"
    TRANSPORTATION = "transportation"
    OFFICE_SUPPLIES = "office_supplies"
    TRAVEL = "travel"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"

# Health Check
class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str

# Receipt Upload Notification
class ReceiptUploadNotification(BaseModel):
    s3_key: str = Field(..., description="S3 object key for uploaded receipt")
    file_size: int = Field(..., gt=0, description="File size in bytes")
    content_type: str = Field(..., description="MIME type of the file")
    uploaded_at: str = Field(..., description="ISO 8601 timestamp")

    @validator('content_type')
    def validate_content_type(cls, v):
        allowed = ["image/jpeg", "image/png", "image/jpg", "application/pdf"]
        if v not in allowed:
            raise ValueError(f"Content type must be one of {allowed}")
        return v

class ReceiptUploadResponse(BaseModel):
    receipt_id: str
    status: ReceiptStatus
    poll_url: str

# OCR Extracted Data
class ConfidenceScores(BaseModel):
    merchant: float = Field(..., ge=0, le=1)
    amount: float = Field(..., ge=0, le=1)
    date: float = Field(..., ge=0, le=1)

class ExtractedData(BaseModel):
    merchant: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = "USD"
    date: Optional[str] = None
    tax: Optional[Decimal] = None
    confidence_scores: Optional[ConfidenceScores] = None

class ErrorDetail(BaseModel):
    code: str
    message: str
    suggestions: List[str] = []

# Receipt Status Response
class ReceiptStatusProcessing(BaseModel):
    receipt_id: str
    status: ReceiptStatus = ReceiptStatus.PROCESSING
    progress: int = Field(..., ge=0, le=100)

class ReceiptStatusCompleted(BaseModel):
    receipt_id: str
    status: ReceiptStatus = ReceiptStatus.COMPLETED
    extracted_data: ExtractedData
    completed_at: str

class ReceiptStatusFailed(BaseModel):
    receipt_id: str
    status: ReceiptStatus = ReceiptStatus.FAILED
    error: ErrorDetail

# User Context
class UserContext(BaseModel):
    user_id: str
    email: str
    company_id: str
    role: str
    cognito_username: str
EOF

# ============================================================================
# BACKEND - Middleware Init
# ============================================================================

touch backend/app/middleware/__init__.py

# ============================================================================
# BACKEND - Auth Middleware
# ============================================================================

cat > backend/app/middleware/auth.py << 'EOF'
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import json
from functools import lru_cache
import requests
from typing import Dict

from app.config import get_settings
from app.models.schemas import UserContext

security = HTTPBearer()
settings = get_settings()

@lru_cache()
def get_cognito_public_keys() -> Dict:
    """Fetch and cache Cognito public keys for JWT verification"""
    region = settings.cognito_region
    user_pool_id = settings.cognito_user_pool_id
    
    keys_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
    
    try:
        response = requests.get(keys_url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch Cognito public keys: {str(e)}"
        )

def verify_jwt_token(token: str) -> Dict:
    """Verify JWT token from Cognito"""
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get('kid')
        
        keys = get_cognito_public_keys()
        
        key = None
        for k in keys.get('keys', []):
            if k.get('kid') == kid:
                key = k
                break
        
        if not key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: Key not found"
            )
        
        payload = jwt.decode(
            token,
            key,
            algorithms=['RS256'],
            audience=settings.cognito_app_client_id,
            options={"verify_exp": True}
        )
        
        return payload
        
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> UserContext:
    """Extract and validate user from JWT token"""
    
    token = credentials.credentials
    
    try:
        payload = verify_jwt_token(token)
        
        user_context = UserContext(
            user_id=payload.get('sub'),
            email=payload.get('email', ''),
            company_id=payload.get('custom:company_id', ''),
            role=payload.get('custom:role', 'employee'),
            cognito_username=payload.get('cognito:username', '')
        )
        
        return user_context
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
EOF

# ============================================================================
# BACKEND - Services Init
# ============================================================================

touch backend/app/services/__init__.py

# ============================================================================
# BACKEND - S3 Service
# ============================================================================

cat > backend/app/services/s3_service.py << 'EOF'
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
EOF

# ============================================================================
# BACKEND - Textract Service
# ============================================================================

cat > backend/app/services/textract_service.py << 'EOF'
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
EOF

# ============================================================================
# BACKEND - DynamoDB Service
# ============================================================================

cat > backend/app/services/dynamodb_service.py << 'EOF'
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
EOF

# ============================================================================
# BACKEND - SNS Service
# ============================================================================

cat > backend/app/services/sns_service.py << 'EOF'
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
EOF

# ============================================================================
# BACKEND - Routers Init
# ============================================================================

touch backend/app/routers/__init__.py

# ============================================================================
# BACKEND - Receipts Router
# ============================================================================

cat > backend/app/routers/receipts.py << 'EOF'
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from typing import Union
import logging

from app.models.schemas import (
    ReceiptUploadNotification, ReceiptUploadResponse,
    ReceiptStatusProcessing, ReceiptStatusCompleted, ReceiptStatusFailed,
    UserContext, ReceiptStatus
)
from app.middleware.auth import get_current_user
from app.services.s3_service import S3Service
from app.services.textract_service import TextractService
from app.services.dynamodb_service import DynamoDBService
from app.services.sns_service import SNSService
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

# Initialize services
s3_service = S3Service()
textract_service = TextractService()
dynamodb_service = DynamoDBService()
sns_service = SNSService()

@router.post("/notify", response_model=ReceiptUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def notify_receipt_upload(
    notification: ReceiptUploadNotification,
    background_tasks: BackgroundTasks,
    current_user: UserContext = Depends(get_current_user)
):
    """
    Notify backend that receipt was uploaded to S3, trigger OCR processing
    
    Flow:
    1. Validate S3 object exists
    2. Verify user owns the object
    3. Create receipt record in DynamoDB
    4. Start Textract OCR job
    5. Return receipt_id for polling
    """
    
    # Validate file size
    if notification.file_size > settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum of {settings.max_file_size} bytes"
        )
    
    # Verify S3 object exists
    if not s3_service.verify_object_exists(notification.s3_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="S3 object not found"
        )
    
    # Verify user owns the S3 object
    if not s3_service.validate_user_owns_object(notification.s3_key, current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not own this S3 object"
        )
    
    try:
        # Start Textract OCR job
        textract_job_id = textract_service.start_expense_analysis(notification.s3_key)
        
        # Create receipt record in DynamoDB
        receipt_id = dynamodb_service.create_receipt_record(
            user_id=current_user.user_id,
            s3_key=notification.s3_key,
            file_size=notification.file_size,
            content_type=notification.content_type,
            textract_job_id=textract_job_id
        )
        
        # Schedule background task to check OCR status
        background_tasks.add_task(
            process_textract_job,
            receipt_id=receipt_id,
            textract_job_id=textract_job_id,
            user_email=current_user.email
        )
        
        logger.info(f"Receipt {receipt_id} processing started for user {current_user.user_id}")
        
        return ReceiptUploadResponse(
            receipt_id=receipt_id,
            status=ReceiptStatus.PROCESSING,
            poll_url=f"/v1/expenses/receipts/{receipt_id}/status"
        )
        
    except Exception as e:
        logger.error(f"Failed to process receipt upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process receipt upload"
        )

@router.get("/{receipt_id}/status", 
            response_model=Union[ReceiptStatusProcessing, ReceiptStatusCompleted, ReceiptStatusFailed])
async def get_receipt_status(
    receipt_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """
    Poll to check if OCR extraction completed
    
    Returns different response based on status:
    - processing: Shows progress percentage
    - completed: Returns extracted data
    - failed: Returns error details
    """
    
    # Get receipt from DynamoDB
    receipt = dynamodb_service.get_receipt(receipt_id)
    
    if not receipt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found"
        )
    
    # Verify user owns the receipt
    if receipt['user_id'] != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    receipt_status = receipt['status']
    
    if receipt_status == ReceiptStatus.PROCESSING.value:
        return ReceiptStatusProcessing(
            receipt_id=receipt_id,
            status=ReceiptStatus.PROCESSING,
            progress=receipt.get('progress', 50)
        )
    
    elif receipt_status == ReceiptStatus.COMPLETED.value:
        return ReceiptStatusCompleted(
            receipt_id=receipt_id,
            status=ReceiptStatus.COMPLETED,
            extracted_data=receipt['extracted_data'],
            completed_at=receipt['completed_at']
        )
    
    elif receipt_status == ReceiptStatus.FAILED.value:
        return ReceiptStatusFailed(
            receipt_id=receipt_id,
            status=ReceiptStatus.FAILED,
            error=receipt['error']
        )

async def process_textract_job(receipt_id: str, textract_job_id: str, user_email: str):
    """
    Background task to check Textract job status and update receipt
    """
    import asyncio
    
    max_attempts = 30  # 30 attempts * 2 seconds = 60 seconds max
    attempt = 0
    
    while attempt < max_attempts:
        try:
            job_status = textract_service.check_job_status(textract