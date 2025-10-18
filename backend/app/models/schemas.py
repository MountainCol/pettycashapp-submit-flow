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
