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
