from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Optional


class AddExpenseRequest(BaseModel):
    description: str = Field(..., min_length=1, description="Expense description")
    amount: float = Field(..., gt=0, description="Expense amount (must be positive)")
    date: datetime = Field(..., description="Expense date")

    @field_validator('description')
    @classmethod
    def description_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Description cannot be empty')
        return v.strip()


class AddExpenseResponse(BaseModel):
    success: bool
    message: str
