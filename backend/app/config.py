import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Settings:
    API_HOST: str = os.getenv('API_HOST', '0.0.0.0')
    API_PORT: int = int(os.getenv('API_PORT', '8000'))
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() == 'true'

    STORAGE_PATH: Path = Path(os.getenv('STORAGE_PATH', './storage'))
    STORAGE_TYPE: str = os.getenv('STORAGE_TYPE', 'local')

    ETHEREUM_RPC_URL: str = os.getenv('ETHEREUM_RPC_URL', 'http://localhost:8545')
    CHAIN_ID: int = int(os.getenv('CHAIN_ID', '1337'))
    PRIVATE_KEY: str = os.getenv('PRIVATE_KEY', '')
    CONTRACT_ADDRESS: str = os.getenv('CONTRACT_ADDRESS', '')

    IPFS_ADDR: str = os.getenv('IPFS_ADDR', '/ip4/127.0.0.1/tcp/5001')

    AWS_ACCESS_KEY_ID: str = os.getenv('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY: str = os.getenv('AWS_SECRET_ACCESS_KEY', '')
    AWS_REGION: str = os.getenv('AWS_REGION', 'us-east-1')
    S3_BUCKET_NAME: str = os.getenv('S3_BUCKET_NAME', '')

    MODEL_PATH: str = os.getenv('MODEL_PATH', 'ml/models/credit_risk_model.pkl')
    SCALER_PATH: str = os.getenv('SCALER_PATH', 'ml/models/feature_scaler.pkl')

    OCR_ENGINE: str = os.getenv('OCR_ENGINE', 'tesseract')
    TESSERACT_CMD: str = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')

    MIN_AGE: int = 18
    MAX_LOAN_AMOUNT: float = 1000.0
    MIN_LOAN_AMOUNT: float = 0.01

    LOW_RISK_THRESHOLD: int = 500
    MEDIUM_RISK_THRESHOLD: int = 1500

settings = Settings()
