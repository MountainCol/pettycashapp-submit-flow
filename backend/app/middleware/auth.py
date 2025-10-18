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
