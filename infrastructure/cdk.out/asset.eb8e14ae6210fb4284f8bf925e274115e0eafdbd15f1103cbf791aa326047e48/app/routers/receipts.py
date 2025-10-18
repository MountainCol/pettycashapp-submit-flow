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
            job_status = textract_service.check_job_status(textract_job_id)
            
            if job_status == 'SUCCEEDED':
                # Get OCR results
                textract_response = textract_service.get_expense_analysis(textract_job_id)
                extracted_data = textract_service.parse_expense_data(textract_response)
                
                if extracted_data:
                    # Update receipt as completed
                    dynamodb_service.update_receipt_status(
                        receipt_id=receipt_id,
                        status=ReceiptStatus.COMPLETED.value,
                        extracted_data=extracted_data.dict(),
                        progress=100
                    )
                    
                    # Send success notification
                    merchant = extracted_data.merchant or "Unknown"
                    amount = str(extracted_data.amount or "0.00")
                    sns_service.send_success_notification(
                        user_email=user_email,
                        receipt_id=receipt_id,
                        merchant=merchant,
                        amount=amount
                    )
                    logger.info(f"Receipt {receipt_id} processed successfully")
                else:
                    # Failed to extract data
                    dynamodb_service.update_receipt_status(
                        receipt_id=receipt_id,
                        status=ReceiptStatus.FAILED.value,
                        error={
                            'code': 'extraction_failed',
                            'message': 'Could not extract receipt data',
                            'suggestions': ['Ensure receipt is clear', 'Try better lighting']
                        }
                    )
                    sns_service.send_failure_notification(
                        user_email=user_email,
                        receipt_id=receipt_id,
                        error_message="Could not extract receipt data. Please upload again."
                    )
                break
            
            elif job_status == 'FAILED':
                # Textract job failed
                dynamodb_service.update_receipt_status(
                    receipt_id=receipt_id,
                    status=ReceiptStatus.FAILED.value,
                    error={
                        'code': 'textract_failed',
                        'message': 'OCR processing failed',
                        'suggestions': ['Check image quality', 'Try a different image']
                    }
                )
                sns_service.send_failure_notification(
                    user_email=user_email,
                    receipt_id=receipt_id,
                    error_message="OCR processing failed. Please upload again."
                )
                break
            
            else:
                # Still processing
                progress = min(50 + (attempt * 2), 95)
                dynamodb_service.update_receipt_status(
                    receipt_id=receipt_id,
                    status=ReceiptStatus.PROCESSING.value,
                    progress=progress
                )
            
            attempt += 1
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Error processing Textract job: {e}")
            break
