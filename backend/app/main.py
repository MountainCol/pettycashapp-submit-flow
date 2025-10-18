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
