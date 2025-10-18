cat > STARR_VIDEO_GUIDE.md << 'EOF'
# PettyCash Receipt Upload Flow - STARR Format Video Guide

## 📋 S - Situation/Scenario

### Business Context
A client needed a **serverless receipt upload and processing system** for their PettyCash application. The system must:

- Allow users to upload receipt photos from mobile/web
- Automatically extract data (merchant, amount, date) using AI/OCR
- Notify users of success or failure
- Handle large files (up to 10MB) without API Gateway limitations
- Be cost-effective and scalable
- Deploy automatically via CI/CD

### Technical Challenge
- **Problem**: API Gateway has a 10MB payload limit, blocking large receipt uploads
- **Solution**: Direct S3 upload → Backend notification → Async OCR processing
- **Architecture**: Serverless (Lambda + S3 + Textract + DynamoDB + SNS)

### Starting Point
- No existing infrastructure
- Need for automated deployment
- Security requirement: No hardcoded credentials

---

## 🎯 T - Task

### Primary Objectives

1. **Create Backend API** (FastAPI on AWS Lambda)
   - Receipt upload notification endpoint
   - Status polling endpoint
   - Cognito JWT authentication
   - Integration with AWS services (S3, Textract, DynamoDB, SNS)

2. **Build Infrastructure as Code** (AWS CDK)
   - S3 bucket for receipt storage
   - DynamoDB table for receipt metadata
   - SNS topic for notifications
   - Cognito user pool for authentication
   - Lambda function with proper IAM permissions
   - API Gateway for HTTP access

3. **Implement CI/CD Pipeline** (GitHub Actions)
   - Automated CDK deployment
   - Secure credential management via GitHub Secrets
   - No local AWS credentials required

4. **Create Frontend Component** (React)
   - File upload with validation
   - Progress tracking
   - Status polling
   - Success/failure notifications

### Success Criteria
✅ Users can upload receipts directly to S3  
✅ Backend processes receipts asynchronously with Textract  
✅ Users receive real-time status updates via polling  
✅ SNS notifications sent on completion  
✅ Infrastructure deploys automatically via GitHub Actions  
✅ No credentials hardcoded in repository  

---

## 🛠️ A - Actions

### Phase 1: Project Setup & Architecture Design

**1.1 Created Setup Script ([setup.sh](cci:7://file:///Users/colinhenderson/Library/CloudStorage/Dropbox/6%20PettyCash-BIC/pettycash-submit-flow/pettycashapp-submit-flow/setup.sh:0:0-0:0))**
```bash
./setup.sh
