# PettyCash Receipt Upload Flow

Complete implementation of receipt upload, OCR processing, and notifications.

## Architecture

```
Frontend (React PWA)
  ↓
Direct S3 Upload (Cognito credentials)
  ↓
API Gateway → Lambda (FastAPI)
  ↓
Textract (OCR) → DynamoDB (Storage) → SNS (Notifications)
```

## Features

✅ **Direct S3 Upload** - Bypasses API Gateway 10MB limit
✅ **Textract OCR** - Automatic receipt data extraction
✅ **Polling System** - Frontend polls for OCR completion
✅ **SNS Notifications** - Success/failure alerts
✅ **Cognito Auth** - JWT token validation
✅ **DynamoDB Storage** - Receipt metadata and status

## Setup

### 1. Run Setup Script

```bash
chmod +x setup.sh
./setup.sh
```

### 2. Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your AWS credentials
```

### 4. Deploy Infrastructure (AWS CDK)

```bash
cd infrastructure
cdk deploy
```

### 5. Run Locally

```bash
cd backend
uvicorn app.main:app --reload
```

## API Endpoints

### POST /v1/expenses/receipts/notify
Notify backend of S3 upload, trigger OCR

**Request:**
```json
{
  "s3_key": "receipts/company_123/user_456/receipt.jpg",
  "file_size": 2458624,
  "content_type": "image/jpeg",
  "uploaded_at": "2025-01-15T10:30:00Z"
}
```

**Response (202):**
```json
{
  "receipt_id": "rec_2KdF8x9mN3pQ",
  "status": "processing",
  "poll_url": "/v1/expenses/receipts/rec_2KdF8x9mN3pQ/status"
}
```

### GET /v1/expenses/receipts/{receipt_id}/status
Poll for OCR completion status

**Response (Processing):**
```json
{
  "receipt_id": "rec_2KdF8x9mN3pQ",
  "status": "processing",
  "progress": 45
}
```

**Response (Completed):**
```json
{
  "receipt_id": "rec_2KdF8x9mN3pQ",
  "status": "completed",
  "extracted_data": {
    "merchant": "Starbucks",
    "amount": 15.50,
    "date": "2025-01-15",
    "currency": "USD"
  },
  "completed_at": "2025-01-15T10:30:12Z"
}
```

## Frontend Usage

```tsx
import { ReceiptUpload } from './components/ReceiptUpload';

function App() {
  return (
    <ReceiptUpload
      onSuccess={(receiptId, data) => {
        console.log('Success!', data);
      }}
      onError={(error) => {
        console.error('Error:', error);
      }}
    />
  );
}
```

## Notifications

**Success:**
- Title: "Receipt Upload Successful! ✅"
- Message: "Your receipt from {merchant} for ${amount} has been successfully processed."
- Action: "create_expense"

**Failure:**
- Title: "Receipt Upload Failed ❌"
- Message: "We couldn't process your receipt. {error_message}"
- Action: "upload_again"

## AWS Resources

- **S3 Bucket**: pettycash-receipts
- **DynamoDB Table**: pettycash-receipts
- **SNS Topic**: pettycash-notifications
- **Cognito User Pool**: pettycash-users
- **Lambda Function**: PettyCash API
- **API Gateway**: PettyCash API

## Testing

```bash
cd backend
pytest
```

## License

MIT
