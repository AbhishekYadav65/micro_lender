"""
Pydantic models for request/response validation
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, Dict, List, Any
from datetime import datetime


# ==================== KYC SCHEMAS ====================

class KYCSubmission(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')
    
    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "John Doe",
                "email": "john@example.com",
                "phone": "+1234567890"
            }
        }


class KYCResponse(BaseModel):
    success: bool
    kyc_hash: str
    verified: bool
    message: str
    data: Optional[Dict[str, Any]] = None


# ==================== ML SCORING SCHEMAS ====================

class ScoreRequest(BaseModel):
    features: Dict[str, float] = Field(..., description="Feature dictionary for ML model")
    
    @validator('features')
    def validate_features(cls, v):
        required_keys = ['income', 'employment_length', 'debt_to_income', 
                        'credit_inquiries', 'loan_amount', 'loan_term']
        missing = set(required_keys) - set(v.keys())
        if missing:
            raise ValueError(f"Missing required features: {missing}")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "features": {
                    "income": 50000.0,
                    "employment_length": 5.0,
                    "debt_to_income": 0.35,
                    "credit_inquiries": 2.0,
                    "loan_amount": 10000.0,
                    "loan_term": 36.0,
                    "num_credit_lines": 5.0,
                    "credit_utilization": 0.3,
                    "payment_history_score": 0.85,
                    "num_delinquencies": 0.0
                }
            }
        }


class ScoreResponse(BaseModel):
    success: bool
    probability_of_default: int = Field(..., description="PD in basis points")
    risk_category: str = Field(..., pattern="^(Low|Medium|High)$")
    explanation_hash: str
    shap_summary: Dict[str, Any]
    storage_url: Optional[str] = None


# ==================== LOAN SCHEMAS ====================

class LoanRequest(BaseModel):
    principal: float = Field(..., gt=0, description="Loan amount in ETH")
    term_days: int = Field(..., ge=7, le=365, description="Loan term in days")
    interest_rate: int = Field(..., ge=0, le=10000, description="Interest rate in basis points")
    
    @validator('principal')
    def validate_principal(cls, v):
        if v < 0.01 or v > 1000:
            raise ValueError("Principal must be between 0.01 and 1000 ETH")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "principal": 1.5,
                "term_days": 90,
                "interest_rate": 1000
            }
        }


class LoanCreationRequest(BaseModel):
    principal: float = Field(..., gt=0)
    term_days: int = Field(..., ge=7, le=365)
    interest_rate: int = Field(..., ge=0, le=10000)
    kyc_hash: str = Field(..., min_length=64, max_length=66)
    explanation_hash: str = Field(..., min_length=64, max_length=66)
    risk_category: str = Field(..., pattern="^(Low|Medium|High)$")
    probability_of_default: int = Field(..., ge=0, le=10000)
    borrower_address: str = Field(..., pattern=r'^0x[a-fA-F0-9]{40}$')
    
    class Config:
        json_schema_extra = {
            "example": {
                "principal": 1.5,
                "term_days": 90,
                "interest_rate": 1000,
                "kyc_hash": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                "explanation_hash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                "risk_category": "Low",
                "probability_of_default": 250,
                "borrower_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"
            }
        }


class LoanResponse(BaseModel):
    success: bool
    loan_id: Optional[int] = None
    transaction_hash: Optional[str] = None
    message: str
    loan_details: Optional[Dict[str, Any]] = None


class LoanDetails(BaseModel):
    loan_id: int
    borrower: str
    principal: float
    interest_rate: int
    term_days: int
    total_repayment: float
    amount_repaid: float
    status: str
    kyc_hash: str
    explanation_hash: str
    created_at: Optional[datetime] = None
    funded_at: Optional[datetime] = None
    disbursed_at: Optional[datetime] = None
    due_date: Optional[datetime] = None


# ==================== COMPLETE WORKFLOW SCHEMA ====================

class CompleteLoanApplication(BaseModel):
    """Schema for end-to-end loan application"""
    # Personal info
    full_name: str
    email: EmailStr
    phone: str
    
    # Loan details
    principal: float = Field(..., gt=0)
    term_days: int = Field(..., ge=7, le=365)
    interest_rate: int = Field(..., ge=0, le=10000)
    borrower_address: str = Field(..., pattern=r'^0x[a-fA-F0-9]{40}$')
    
    # Credit features
    income: float = Field(..., gt=0)
    employment_length: int = Field(..., ge=0)
    debt_to_income: float = Field(..., ge=0, le=1)
    credit_inquiries: int = Field(..., ge=0)
    num_credit_lines: Optional[int] = Field(5, ge=0)
    credit_utilization: Optional[float] = Field(0.3, ge=0, le=1)
    payment_history_score: Optional[float] = Field(0.8, ge=0, le=1)
    num_delinquencies: Optional[int] = Field(0, ge=0)


class CompleteApplicationResponse(BaseModel):
    success: bool
    message: str
    kyc: Dict[str, Any]
    credit_score: Dict[str, Any]
    loan: Dict[str, Any]


# ==================== ERROR SCHEMAS ====================

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ==================== HEALTH CHECK SCHEMA ====================

class HealthCheckResponse(BaseModel):
    status: str
    services: Dict[str, bool]
    timestamp: datetime = Field(default_factory=datetime.utcnow)