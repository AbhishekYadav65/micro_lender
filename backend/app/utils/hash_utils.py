"""
hash_utils.py - SHA256 hashing utilities
"""
import hashlib
import json
from typing import Dict, Any


def generate_hash(data: Dict[str, Any]) -> str:
    """
    Generate SHA256 hash from dictionary
    
    Args:
        data: Dictionary to hash
        
    Returns:
        Hex string of SHA256 hash
    """
    # Convert to JSON string with sorted keys for consistency
    json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
    
    # Generate SHA256 hash
    hash_obj = hashlib.sha256(json_str.encode('utf-8'))
    
    return '0x' + hash_obj.hexdigest()


def verify_hash(data: Dict[str, Any], expected_hash: str) -> bool:
    """
    Verify that data matches expected hash
    
    Args:
        data: Dictionary to verify
        expected_hash: Expected hash value
        
    Returns:
        True if hash matches, False otherwise
    """
    computed_hash = generate_hash(data)
    return computed_hash.lower() == expected_hash.lower()


# ==================== kyc_service.py ====================

"""
KYC Service for verification logic
"""
from datetime import datetime, timedelta
from typing import Optional
import re
from difflib import SequenceMatcher


class KYCService:
    def __init__(self):
        """Initialize KYC service"""
        self.min_age = 18
        self.kyc_records = {}  # In-memory storage for demo
    
    def verify_age(self, date_of_birth: Optional[str]) -> bool:
        """
        Verify that person is at least 18 years old
        
        Args:
            date_of_birth: Date of birth in YYYY-MM-DD format
            
        Returns:
            True if age >= 18, False otherwise
        """
        if not date_of_birth:
            return False
        
        try:
            # Parse date
            dob = datetime.strptime(date_of_birth, "%Y-%m-%d")
            
            # Calculate age
            today = datetime.now()
            age = today.year - dob.year
            
            # Adjust if birthday hasn't occurred this year
            if today.month < dob.month or (today.month == dob.month and today.day < dob.day):
                age -= 1
            
            return age >= self.min_age
            
        except (ValueError, AttributeError):
            return False
    
    def verify_name_match(self, form_name: str, extracted_name: str, threshold: float = 0.8) -> bool:
        """
        Verify that form name matches extracted name from ID
        
        Uses fuzzy matching to account for OCR errors and formatting differences
        
        Args:
            form_name: Name entered in form
            extracted_name: Name extracted from ID document
            threshold: Similarity threshold (0-1)
            
        Returns:
            True if names match sufficiently, False otherwise
        """
        if not form_name or not extracted_name:
            return False
        
        # Normalize names
        form_normalized = self._normalize_name(form_name)
        extracted_normalized = self._normalize_name(extracted_name)
        
        # Calculate similarity
        similarity = SequenceMatcher(None, form_normalized, extracted_normalized).ratio()
        
        # Also check if one name is contained in the other (for middle name differences)
        contained = (
            form_normalized in extracted_normalized or 
            extracted_normalized in form_normalized
        )
        
        return similarity >= threshold or contained
    
    def _normalize_name(self, name: str) -> str:
        """Normalize name for comparison"""
        # Convert to lowercase
        normalized = name.lower()
        
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        
        # Remove special characters except spaces and hyphens
        normalized = re.sub(r'[^\w\s\-]', '', normalized)
        
        return normalized
    
    def store_kyc(self, kyc_hash: str, kyc_data: dict):
        """Store KYC record"""
        self.kyc_records[kyc_hash] = {
            'data': kyc_data,
            'verified': True,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def kyc_exists(self, kyc_hash: str) -> bool:
        """Check if KYC hash exists"""
        return kyc_hash in self.kyc_records
    
    def get_kyc_status(self, kyc_hash: str) -> Optional[dict]:
        """Get KYC verification status"""
        return self.kyc_records.get(kyc_hash)
    
    def validate_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def validate_phone(self, phone: str) -> bool:
        """Validate phone number format"""
        # Remove all non-digit characters
        digits = re.sub(r'\D', '', phone)
        
        # Check length (typically 10-15 digits)
        return 10 <= len(digits) <= 15