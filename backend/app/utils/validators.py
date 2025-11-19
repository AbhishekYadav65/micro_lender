"""
Input validators
"""
from typing import Any, Optional
import re


def validate_ethereum_address(address: str) -> bool:
    """Validate Ethereum address format"""
    if not address:
        return False
    
    # Check format: 0x followed by 40 hex characters
    pattern = r'^0x[a-fA-F0-9]{40}$'
    return bool(re.match(pattern, address))


def validate_hash(hash_value: str) -> bool:
    """Validate SHA256 hash format"""
    if not hash_value:
        return False
    
    # Check format: 0x followed by 64 hex characters
    pattern = r'^0x[a-fA-F0-9]{64}$'
    return bool(re.match(pattern, hash_value))


def validate_principal(amount: float, min_amount: float = 0.01, max_amount: float = 1000.0) -> bool:
    """Validate loan principal amount"""
    try:
        return min_amount <= float(amount) <= max_amount
    except (ValueError, TypeError):
        return False


def validate_interest_rate(rate: int, max_rate: int = 10000) -> bool:
    """Validate interest rate in basis points"""
    try:
        return 0 <= int(rate) <= max_rate
    except (ValueError, TypeError):
        return False


def validate_term_days(days: int, min_days: int = 7, max_days: int = 365) -> bool:
    """Validate loan term in days"""
    try:
        return min_days <= int(days) <= max_days
    except (ValueError, TypeError):
        return False


def validate_risk_category(category: str) -> bool:
    """Validate risk category"""
    valid_categories = ['Low', 'Medium', 'High']
    return category in valid_categories


def sanitize_input(input_str: str, max_length: int = 1000) -> str:
    """Sanitize user input"""
    if not input_str:
        return ""
    
    # Truncate to max length
    sanitized = str(input_str)[:max_length]
    
    # Remove null bytes
    sanitized = sanitized.replace('\x00', '')
    
    return sanitized.strip()