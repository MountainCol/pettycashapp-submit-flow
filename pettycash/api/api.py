from fastapi import APIRouter

from pettycash.api.endpoints import expenses

router = APIRouter()
router.include_router(expenses.router, prefix="/expenses", tags=["Expenses"])
