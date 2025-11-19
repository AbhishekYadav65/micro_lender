from fastapi import APIRouter, HTTPException
from app.services.blockchain_service import BlockchainService
from app.models.schemas import LoanCreationRequest, LoanResponse


router = APIRouter(prefix="/api/loan", tags=["Loan"])
blockchain = BlockchainService()


@router.post("/create", response_model=LoanResponse)
async def create_loan(request: LoanCreationRequest):

    tx = blockchain.create_loan(
        principal=request.principal,
        term_days=request.term_days,
        interest_rate=request.interest_rate,
        kyc_hash=request.kyc_hash,
        explanation_hash=request.explanation_hash,
        risk_category=request.risk_category,
        probability_of_default=request.probability_of_default,
        borrower_address=request.borrower_address
    )

    if not tx.get("success"):
        raise HTTPException(status_code=500, detail=tx["error"])

    return {
        "success": True,
        "loan_id": tx.get("loan_id"),
        "transaction_hash": tx.get("tx_hash"),
        "message": "Loan created successfully"
    }
