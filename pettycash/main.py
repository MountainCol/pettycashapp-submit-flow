from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pettycash.api.api import router

app = FastAPI(title="PettyCash", description="Expense Management")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "PettyCash API - Use /docs to learn more"}

app.include_router(router)
