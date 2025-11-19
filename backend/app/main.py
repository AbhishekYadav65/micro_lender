"""
FastAPI Backend for P2P Micro-Lending Platform
Main application entry point
"""
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import uvicorn
from datetime import datetime
import logging

from app.services.kyc_service import KYCService
from app.services.ocr_service import OCRService
from app.services.ml_service import MLService
from app.services.storage_service import StorageService
from app.services.blockchain_service import BlockchainService
from app.models.schemas import (
    KYCSubmission, KYCResponse, LoanRequest, LoanResponse, 
    ScoreRequest, ScoreResponse, LoanCreationRequest
)
from app.utils.hash_utils import generate_hash
from app.routes.kyc_routes import router as kyc_router
from app.routes.ml_routes import router as ml_router
from app.routes.loan_routes import router as loan_router



# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="P2P Micro-Lending Platform API",
    description="Complete P2P lending platform with KYC, ML scoring, and blockchain integration",
    version="1.0.0"
)

app.include_router(kyc_router)
app.include_router(ml_router)
app.include_router(loan_router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
kyc_service = KYCService()
ocr_service = OCRService()
ml_service = MLService()
storage_service = StorageService()
blockchain_service = BlockchainService()

# Health check endpoint
@app.get("/")
async def root():
    return {
        "service": "P2P Micro-Lending Platform",
        "status": "operational",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "services": {
            "ocr": ocr_service.check_health(),
            "ml": ml_service.check_health(),
            "storage": storage_service.check_health(),
            "blockchain": blockchain_service.check_health()
        }
    }

# ==================== KYC ENDPOINTS ====================

@app.post("/api/kyc/submit", response_model=KYCResponse)
async def submit_kyc(
    id_document: UploadFile = File(...),
    selfie: UploadFile = File(...),
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...)
):
    """
    Submit KYC documents for verification
    
    Process:
    1. Upload and validate documents
    2. Run OCR on ID document
    3. Extract KYC data (name, DOB, ID number)
    4. Verify age >= 18
    5. Match name with form input
    6. Generate KYC_HASH
    7. Store documents
    """
    try:
        logger.info(f"KYC submission received for {email}")
        
        # Step 1: Validate file types
        if not id_document.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="ID document must be an image")
        if not selfie.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Selfie must be an image")
        
        # Step 2: Read file contents
        id_doc_bytes = await id_document.read()
        selfie_bytes = await selfie.read()
        
        # Step 3: Run OCR on ID document
        logger.info("Running OCR on ID document...")
        ocr_result = ocr_service.process_id_document(id_doc_bytes)
        
        if not ocr_result.get('success'):
            raise HTTPException(
                status_code=400, 
                detail=f"OCR processing failed: {ocr_result.get('error', 'Unknown error')}"
            )
        
        extracted_data = ocr_result['data']
        logger.info(f"OCR extracted: {extracted_data}")
        
        # Step 4: Verify age >= 18
        if not kyc_service.verify_age(extracted_data.get('date_of_birth')):
            raise HTTPException(
                status_code=400, 
                detail="Applicant must be at least 18 years old"
            )
        
        # Step 5: Match name with form input
        if not kyc_service.verify_name_match(full_name, extracted_data.get('name', '')):
            raise HTTPException(
                status_code=400, 
                detail="Name on ID document does not match submitted name"
            )
        
        # Step 6: Create KYC JSON
        kyc_data = {
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "extracted_name": extracted_data.get('name'),
            "date_of_birth": extracted_data.get('date_of_birth'),
            "id_number": extracted_data.get('id_number'),
            "id_type": extracted_data.get('id_type', 'unknown'),
            "verification_timestamp": datetime.utcnow().isoformat(),
            "age_verified": True,
            "name_verified": True
        }
        
        # Step 7: Generate KYC_HASH
        kyc_hash = generate_hash(kyc_data)
        logger.info(f"Generated KYC_HASH: {kyc_hash}")
        
        # Step 8: Store documents and KYC data
        storage_result = storage_service.store_kyc_documents(
            kyc_hash=kyc_hash,
            id_document=id_doc_bytes,
            selfie=selfie_bytes,
            kyc_data=kyc_data
        )
        
        if not storage_result.get('success'):
            raise HTTPException(
                status_code=500,
                detail=f"Storage failed: {storage_result.get('error')}"
            )
        
        return KYCResponse(
            success=True,
            kyc_hash=kyc_hash,
            verified=True,
            message="KYC verification successful",
            data={
                "name": full_name,
                "email": email,
                "age_verified": True,
                "name_verified": True,
                "storage_url": storage_result.get('url')
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"KYC submission error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/api/kyc/status/{kyc_hash}")
async def get_kyc_status(kyc_hash: str):
    """Get KYC verification status by hash"""
    try:
        status = kyc_service.get_kyc_status(kyc_hash)
        if not status:
            raise HTTPException(status_code=404, detail="KYC record not found")
        return status
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== ML SCORING ENDPOINTS ====================

@app.post("/api/score/predict", response_model=ScoreResponse)
async def predict_credit_score(request: ScoreRequest):
    """
    Predict credit risk score using ML model
    
    Process:
    1. Validate input features
    2. Run ML model prediction
    3. Generate SHAP explanations
    4. Store explanation JSON
    5. Generate EXPLANATION_HASH
    6. Return score and hash
    """
    try:
        logger.info(f"Credit scoring request received")
        
        # Step 1: Validate features
        features = request.features
        if not ml_service.validate_features(features):
            raise HTTPException(status_code=400, detail="Invalid feature set")
        
        # Step 2: Run prediction
        prediction_result = ml_service.predict(features)
        
        if not prediction_result.get('success'):
            raise HTTPException(
                status_code=500,
                detail=f"Prediction failed: {prediction_result.get('error')}"
            )
        
        # Step 3: Generate SHAP explanations
        logger.info("Generating SHAP explanations...")
        explanation = ml_service.generate_shap_explanation(features)
        
        if not explanation.get('success'):
            raise HTTPException(
                status_code=500,
                detail=f"SHAP generation failed: {explanation.get('error')}"
            )
        
        # Step 4: Create explanation JSON
        explanation_data = {
            "features": features,
            "prediction": prediction_result['prediction'],
            "probability_of_default": prediction_result['probability'],
            "risk_category": prediction_result['risk_category'],
            "shap_values": explanation['shap_values'],
            "feature_importance": explanation['feature_importance'],
            "base_value": explanation['base_value'],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Step 5: Generate EXPLANATION_HASH
        explanation_hash = generate_hash(explanation_data)
        logger.info(f"Generated EXPLANATION_HASH: {explanation_hash}")
        
        # Step 6: Store explanation
        storage_result = storage_service.store_explanation(
            explanation_hash=explanation_hash,
            explanation_data=explanation_data
        )
        
        if not storage_result.get('success'):
            logger.warning(f"Failed to store explanation: {storage_result.get('error')}")
        
        return ScoreResponse(
            success=True,
            probability_of_default=prediction_result['probability'],
            risk_category=prediction_result['risk_category'],
            explanation_hash=explanation_hash,
            shap_summary={
                "top_features": explanation['feature_importance'][:5],
                "base_value": explanation['base_value']
            },
            storage_url=storage_result.get('url')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Scoring error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/api/score/explanation/{explanation_hash}")
async def get_explanation(explanation_hash: str):
    """Retrieve full SHAP explanation by hash"""
    try:
        explanation = storage_service.retrieve_explanation(explanation_hash)
        if not explanation:
            raise HTTPException(status_code=404, detail="Explanation not found")
        return explanation
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== LOAN ENDPOINTS ====================

@app.post("/api/loans/create", response_model=LoanResponse)
async def create_loan(request: LoanCreationRequest):
    """
    Create a loan on the blockchain
    
    Process:
    1. Validate KYC_HASH exists
    2. Validate EXPLANATION_HASH exists
    3. Call smart contract createLoan()
    4. Return transaction details
    """
    try:
        logger.info(f"Loan creation request: {request.principal} ETH")
        
        # Step 1: Verify KYC exists
        if not kyc_service.kyc_exists(request.kyc_hash):
            raise HTTPException(status_code=400, detail="Invalid KYC hash")
        
        # Step 2: Verify explanation exists
        if not storage_service.explanation_exists(request.explanation_hash):
            raise HTTPException(status_code=400, detail="Invalid explanation hash")
        
        # Step 3: Create loan on blockchain
        tx_result = blockchain_service.create_loan(
            principal=request.principal,
            term_days=request.term_days,
            interest_rate=request.interest_rate,
            kyc_hash=request.kyc_hash,
            explanation_hash=request.explanation_hash,
            risk_category=request.risk_category,
            probability_of_default=request.probability_of_default,
            borrower_address=request.borrower_address
        )
        
        if not tx_result.get('success'):
            raise HTTPException(
                status_code=500,
                detail=f"Blockchain transaction failed: {tx_result.get('error')}"
            )
        
        return LoanResponse(
            success=True,
            loan_id=tx_result['loan_id'],
            transaction_hash=tx_result['tx_hash'],
            message="Loan created successfully",
            loan_details={
                "principal": request.principal,
                "term_days": request.term_days,
                "interest_rate": request.interest_rate,
                "risk_category": request.risk_category,
                "kyc_hash": request.kyc_hash,
                "explanation_hash": request.explanation_hash
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Loan creation error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/api/loans/{loan_id}")
async def get_loan(loan_id: int):
    """Get loan details from blockchain"""
    try:
        loan_details = blockchain_service.get_loan(loan_id)
        if not loan_details:
            raise HTTPException(status_code=404, detail="Loan not found")
        return loan_details
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/loans/borrower/{address}")
async def get_borrower_loans(address: str):
    """Get all loans for a borrower address"""
    try:
        loans = blockchain_service.get_borrower_loans(address)
        return {"address": address, "loans": loans}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/loans/{loan_id}/fund")
async def fund_loan(loan_id: int, amount: float, lender_address: str):
    """Fund a loan"""
    try:
        result = blockchain_service.fund_loan(loan_id, amount, lender_address)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/loans/{loan_id}/disburse")
async def disburse_loan(loan_id: int, borrower_address: str):
    """Disburse loan funds to borrower"""
    try:
        result = blockchain_service.disburse_loan(loan_id, borrower_address)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/loans/{loan_id}/repay")
async def repay_loan(loan_id: int, amount: float, borrower_address: str):
    """Make a repayment on a loan"""
    try:
        result = blockchain_service.repay_loan(loan_id, amount, borrower_address)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== END-TO-END WORKFLOW ENDPOINT ====================

@app.post("/api/workflow/complete-loan-application")
async def complete_loan_application(
    id_document: UploadFile = File(...),
    selfie: UploadFile = File(...),
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    principal: float = Form(...),
    term_days: int = Form(...),
    interest_rate: int = Form(...),
    borrower_address: str = Form(...),
    # Feature inputs for ML model
    income: float = Form(...),
    employment_length: int = Form(...),
    debt_to_income: float = Form(...),
    credit_inquiries: int = Form(...)
):
    """
    Complete end-to-end loan application workflow
    
    Steps:
    1. KYC verification
    2. ML credit scoring
    3. Blockchain loan creation
    """
    try:
        logger.info(f"Complete loan application for {email}")
        
        # STEP 1: KYC Verification
        logger.info("Step 1: Processing KYC...")
        id_doc_bytes = await id_document.read()
        selfie_bytes = await selfie.read()
        
        ocr_result = ocr_service.process_id_document(id_doc_bytes)
        if not ocr_result.get('success'):
            raise HTTPException(status_code=400, detail="KYC verification failed")
        
        extracted_data = ocr_result['data']
        
        if not kyc_service.verify_age(extracted_data.get('date_of_birth')):
            raise HTTPException(status_code=400, detail="Age verification failed")
        
        if not kyc_service.verify_name_match(full_name, extracted_data.get('name', '')):
            raise HTTPException(status_code=400, detail="Name verification failed")
        
        kyc_data = {
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "extracted_name": extracted_data.get('name'),
            "date_of_birth": extracted_data.get('date_of_birth'),
            "id_number": extracted_data.get('id_number'),
            "verification_timestamp": datetime.utcnow().isoformat()
        }
        
        kyc_hash = generate_hash(kyc_data)
        storage_service.store_kyc_documents(kyc_hash, id_doc_bytes, selfie_bytes, kyc_data)
        
        logger.info(f"✓ KYC complete. Hash: {kyc_hash}")
        
        # STEP 2: ML Credit Scoring
        logger.info("Step 2: Running ML credit scoring...")
        features = {
            "income": income,
            "employment_length": employment_length,
            "debt_to_income": debt_to_income,
            "credit_inquiries": credit_inquiries,
            "loan_amount": principal,
            "loan_term": term_days
        }
        
        prediction_result = ml_service.predict(features)
        if not prediction_result.get('success'):
            raise HTTPException(status_code=500, detail="Credit scoring failed")
        
        explanation = ml_service.generate_shap_explanation(features)
        
        explanation_data = {
            "features": features,
            "prediction": prediction_result['prediction'],
            "probability_of_default": prediction_result['probability'],
            "risk_category": prediction_result['risk_category'],
            "shap_values": explanation['shap_values'],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        explanation_hash = generate_hash(explanation_data)
        storage_service.store_explanation(explanation_hash, explanation_data)
        
        logger.info(f"✓ ML scoring complete. Risk: {prediction_result['risk_category']}, Hash: {explanation_hash}")
        
        # STEP 3: Blockchain Loan Creation
        logger.info("Step 3: Creating loan on blockchain...")
        tx_result = blockchain_service.create_loan(
            principal=principal,
            term_days=term_days,
            interest_rate=interest_rate,
            kyc_hash=kyc_hash,
            explanation_hash=explanation_hash,
            risk_category=prediction_result['risk_category'],
            probability_of_default=prediction_result['probability'],
            borrower_address=borrower_address
        )
        
        if not tx_result.get('success'):
            raise HTTPException(status_code=500, detail="Blockchain transaction failed")
        
        logger.info(f"✓ Loan created on blockchain. Loan ID: {tx_result['loan_id']}")
        
        return {
            "success": True,
            "message": "Loan application completed successfully",
            "kyc": {
                "hash": kyc_hash,
                "verified": True
            },
            "credit_score": {
                "risk_category": prediction_result['risk_category'],
                "probability_of_default": prediction_result['probability'],
                "explanation_hash": explanation_hash
            },
            "loan": {
                "loan_id": tx_result['loan_id'],
                "transaction_hash": tx_result['tx_hash'],
                "principal": principal,
                "term_days": term_days,
                "interest_rate": interest_rate
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complete application error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)