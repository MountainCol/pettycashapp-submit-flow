from fastapi import APIRouter
from pettycash.api.models.models import AddExpenseRequest, AddExpenseResponse

router = APIRouter()


@router.post("/add", response_model=AddExpenseResponse)
async def add_expense(request: AddExpenseRequest):
    # TODO: Implement actual expense storage logic
    return AddExpenseResponse(
        success=True,
        message="Expense added successfully"
    )
