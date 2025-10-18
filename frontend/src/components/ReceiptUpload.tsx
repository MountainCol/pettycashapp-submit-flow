import React, { useState, useRef } from 'react';
import { Camera, Upload, CheckCircle, XCircle, Loader } from 'lucide-react';

interface ReceiptUploadProps {
  onSuccess?: (receiptId: string, extractedData: any) => void;
  onError?: (error: string) => void;
}

export const ReceiptUpload: React.FC<ReceiptUploadProps> = ({ onSuccess, onError }) => {
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<'idle' | 'uploading' | 'processing' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    const allowedTypes = ['image/jpeg', 'image/png', 'image/jpg', 'application/pdf'];
    if (!allowedTypes.includes(file.type)) {
      setStatus('error');
      setMessage('Invalid file type. Please upload a JPEG, PNG, or PDF.');
      onError?.('Invalid file type');
      return;
    }

    // Validate file size (10MB max)
    if (file.size > 10485760) {
      setStatus('error');
      setMessage('File too large. Maximum size is 10MB.');
      onError?.('File too large');
      return;
    }

    await uploadReceipt(file);
  };

  const uploadReceipt = async (file: File) => {
    try {
      setUploading(true);
      setStatus('uploading');
      setMessage('Uploading receipt...');

      // Step 1: Get presigned URL from Cognito credentials
      // (In production, use AWS Amplify or Cognito Identity Pool)
      const s3Key = `receipts/company_123/user_${Date.now()}/${file.name}`;
      
      // Step 2: Upload to S3 (simplified - use AWS SDK in production)
      // await uploadToS3(file, s3Key);

      // Step 3: Notify backend
      const response = await fetch('/v1/expenses/receipts/notify', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('jwt_token')}`
        },
        body: JSON.stringify({
          s3_key: s3Key,
          file_size: file.size,
          content_type: file.type,
          uploaded_at: new Date().toISOString()
        })
      });

      if (!response.ok) throw new Error('Upload notification failed');

      const data = await response.json();
      setUploading(false);
      setProcessing(true);
      setStatus('processing');
      setMessage('Processing receipt with OCR...');

      // Step 4: Poll for OCR results
      await pollReceiptStatus(data.receipt_id);

    } catch (error) {
      setStatus('error');
      setMessage('Upload failed. Please try again.');
      setUploading(false);
      setProcessing(false);
      onError?.(error instanceof Error ? error.message : 'Upload failed');
    }
  };

  const pollReceiptStatus = async (receiptId: string) => {
    const maxAttempts = 30;
    let attempt = 0;

    const poll = async () => {
      try {
        const response = await fetch(`/v1/expenses/receipts/${receiptId}/status`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('jwt_token')}`
          }
        });

        if (!response.ok) throw new Error('Failed to check status');

        const data = await response.json();

        if (data.status === 'completed') {
          setStatus('success');
          setMessage('Receipt processed successfully! ✅');
          setProcessing(false);
          setProgress(100);
          onSuccess?.(receiptId, data.extracted_data);
          return;
        } else if (data.status === 'failed') {
          setStatus('error');
          setMessage(data.error?.message || 'Processing failed. Please upload again.');
          setProcessing(false);
          onError?.(data.error?.message);
          return;
        } else {
          // Still processing
          setProgress(data.progress || 50);
          attempt++;
          if (attempt < maxAttempts) {
            setTimeout(poll, 2000);
          } else {
            throw new Error('Processing timeout');
          }
        }
      } catch (error) {
        setStatus('error');
        setMessage('Failed to check status');
        setProcessing(false);
        onError?.(error instanceof Error ? error.message : 'Status check failed');
      }
    };

    poll();
  };

  return (
    <div className="max-w-md mx-auto p-6 bg-white rounded-lg shadow-lg">
      <h2 className="text-2xl font-bold mb-4">Upload Receipt</h2>
      
      <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
        {status === 'idle' && (
          <>
            <Upload className="mx-auto h-12 w-12 text-gray-400 mb-4" />
            <p className="text-gray-600 mb-4">Click to upload or drag and drop</p>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/jpg,application/pdf"
              onChange={handleFileSelect}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Select Receipt
            </button>
          </>
        )}

        {(status === 'uploading' || status === 'processing') && (
          <>
            <Loader className="mx-auto h-12 w-12 text-blue-600 animate-spin mb-4" />
            <p className="text-gray-700 font-medium">{message}</p>
            {processing && (
              <div className="mt-4">
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="text-sm text-gray-600 mt-2">{progress}%</p>
              </div>
            )}
          </>
        )}

        {status === 'success' && (
          <>
            <CheckCircle className="mx-auto h-12 w-12 text-green-600 mb-4" />
            <p className="text-green-700 font-medium">{message}</p>
            <button
              onClick={() => {
                setStatus('idle');
                setMessage('');
                setProgress(0);
              }}
              className="mt-4 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
            >
              Upload Another
            </button>
          </>
        )}

        {status === 'error' && (
          <>
            <XCircle className="mx-auto h-12 w-12 text-red-600 mb-4" />
            <p className="text-red-700 font-medium">{message}</p>
            <button
              onClick={() => {
                setStatus('idle');
                setMessage('');
              }}
              className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
            >
              Try Again
            </button>
          </>
        )}
      </div>
    </div>
  );
};
