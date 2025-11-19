"""
KYC Service
Provides:
 - age verification
 - name matching (fuzzy using difflib)
 - simple in-memory storage of KYC records with JSON persistence
"""

from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Dict, Any
import logging
from difflib import SequenceMatcher

from app.config import settings

logger = logging.getLogger(__name__)


class KYCService:
    def __init__(self):
        # storage path for lightweight persistence
        storage_root = Path(settings.STORAGE_PATH or "./storage")
        storage_root.mkdir(parents=True, exist_ok=True)
        self._store_path = storage_root / "kyc_records.json"

        # in-memory records: { kyc_hash: record_dict }
        self.kyc_records: Dict[str, Dict[str, Any]] = {}
        self._load()

    # -------------------------
    # Persistence helpers
    # -------------------------
    def _load(self) -> None:
        try:
            if self._store_path.exists():
                with open(self._store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.kyc_records = data
                    else:
                        logger.warning("KYC store file malformed; starting fresh.")
                        self.kyc_records = {}
            else:
                self.kyc_records = {}
        except Exception as e:
            logger.error(f"Failed to load KYC records: {e}", exc_info=True)
            self.kyc_records = {}

    def _save(self) -> None:
        try:
            with open(self._store_path, "w", encoding="utf-8") as f:
                json.dump(self.kyc_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save KYC records: {e}", exc_info=True)

    # -------------------------
    # Public API
    # -------------------------
    def add_kyc_record(self, kyc_hash: str, kyc_data: Dict[str, Any]) -> bool:
        """
        Add or update a KYC record (and persist).
        kyc_data should be serializable to JSON.
        """
        try:
            self.kyc_records[kyc_hash] = {
                "kyc_hash": kyc_hash,
                "data": kyc_data,
                "created_at": datetime.utcnow().isoformat()
            }
            self._save()
            return True
        except Exception as e:
            logger.error(f"Failed to add KYC record: {e}", exc_info=True)
            return False

    def get_kyc_status(self, kyc_hash: str) -> Optional[Dict[str, Any]]:
        """
        Return the stored KYC record by hash or None.
        """
        return self.kyc_records.get(kyc_hash)

    def kyc_exists(self, kyc_hash: str) -> bool:
        return kyc_hash in self.kyc_records

    # -------------------------
    # Validation utilities
    # -------------------------
    def verify_age(self, dob_str: Optional[str]) -> bool:
        """
        Verify the applicant is at least settings.MIN_AGE years old.
        Accepts dob_str in common formats: YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, Month DD, YYYY
        Returns False if dob_str is None or unparsable.
        """
        if not dob_str:
            return False

        dob = self._parse_date_string(dob_str)
        if not dob:
            return False

        today = date.today()
        # compute full years
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return age >= settings.MIN_AGE

    def verify_name_match(self, submitted_name: str, extracted_name: Optional[str], threshold: float = 0.80) -> bool:
        """
        Fuzzy name matching using SequenceMatcher.
        Returns True when similarity >= threshold.
        If extracted_name is None or empty, returns False.
        """
        if not submitted_name or not extracted_name:
            return False

        a = self._normalize_name(submitted_name)
        b = self._normalize_name(extracted_name)

        # if exact match after normalization, accept immediately
        if a == b:
            return True

        ratio = SequenceMatcher(None, a, b).ratio()
        logger.debug(f"Name match ratio: {ratio:.3f} for '{a}' vs '{b}'")
        return ratio >= threshold

    # -------------------------
    # Helpers
    # -------------------------
    def _normalize_name(self, name: str) -> str:
        # Lowercase, strip common punctuation, collapse spaces
        cleaned = "".join(ch for ch in name if ch.isalnum() or ch.isspace())
        cleaned = " ".join(cleaned.lower().split())
        return cleaned

    def _parse_date_string(self, s: str) -> Optional[date]:
        s = s.strip()
        # common formats to try
        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d %b %Y",     # 01 Jan 2000
            "%d %B %Y",     # 01 January 2000
            "%b %d %Y",     # Jan 01 2000
            "%B %d %Y",     # January 01 2000
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(s, fmt).date()
                return dt
            except Exception:
                continue

        # Try to extract three groups of digits (e.g., DD MM YYYY or YYYY MM DD)
        import re
        m = re.search(r"(\d{1,4})\D+(\d{1,2})\D+(\d{1,4})", s)
        if m:
            g1, g2, g3 = m.groups()
            # heuristics: if g1 has 4 digits, assume YYYY MM DD
            try:
                if len(g1) == 4:
                    year = int(g1); month = int(g2); day = int(g3)
                elif len(g3) == 4:
                    day = int(g1); month = int(g2); year = int(g3)
                else:
                    # fallback: assume day, month, year
                    day = int(g1); month = int(g2); year = int(g3)
                return date(year, month, day)
            except Exception:
                return None

        return None
