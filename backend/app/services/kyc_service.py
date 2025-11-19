import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, date
import logging
import cv2
import numpy as np
from difflib import SequenceMatcher

from app.config import settings
from app.services.ocr_service import OCRService
from app.services.storage_service import StorageService


logger = logging.getLogger(__name__)


class KYCService:
    def __init__(self):
        storage_root = Path(settings.STORAGE_PATH or "./storage")
        storage_root.mkdir(parents=True, exist_ok=True)
        self._store_path = storage_root / "kyc_records.json"

        self.kyc_records: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ======================================================
    # Persistence
    # ======================================================
    def _load(self):
        try:
            if self._store_path.exists():
                with open(self._store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.kyc_records = data if isinstance(data, dict) else {}
        except:
            self.kyc_records = {}

    def _save(self):
        try:
            with open(self._store_path, "w", encoding="utf-8") as f:
                json.dump(self.kyc_records, f, indent=2)
        except Exception as e:
            logger.error(f"Failed saving KYC records: {e}")

    def add_kyc_record(self, kyc_hash: str, data: Dict[str, Any]):
        self.kyc_records[kyc_hash] = {
            "kyc_hash": kyc_hash,
            "data": data,
            "created_at": datetime.utcnow().isoformat()
        }
        self._save()

    # ======================================================
    # Public API — main KYC workflow
    # ======================================================
    async def verify_kyc(
        self,
        full_name: str,
        email: str,
        phone: str,
        id_document_bytes: bytes,
        selfie_bytes: bytes
    ) -> Dict[str, Any]:

        ocr = OCRService()
        storage = StorageService()

        # 1) OCR
        ocr_result = ocr.process_id_document(id_document_bytes)
        if not ocr_result.get("success"):
            return {"success": False, "verified": False, "message": "OCR failed"}

        extracted = ocr_result["data"]
        extracted_name = extracted.get("name")
        extracted_dob = extracted.get("date_of_birth")
        extracted_id = extracted.get("id_number")

        # 2) Name match
        if not self.verify_name_match(full_name, extracted_name):
            return {
                "success": False,
                "verified": False,
                "message": "Name mismatch",
                "data": {"submitted": full_name, "ocr": extracted_name}
            }

        # 3) Age check
        if not self.verify_age(extracted_dob):
            return {
                "success": False,
                "verified": False,
                "message": "User does not meet minimum age",
                "data": {"dob": extracted_dob}
            }

        # 4) Face comparison
        if not self._compare_faces(id_document_bytes, selfie_bytes):
            return {"success": False, "verified": False, "message": "Face mismatch"}

        # 5) Create hash
        combined = f"{full_name}{email}{phone}{extracted_name}{extracted_dob}{extracted_id}"
        kyc_hash = hashlib.sha256(combined.encode()).hexdigest()

        # 6) Save
        record = {
            "submitted_name": full_name,
            "email": email,
            "phone": phone,
            "ocr_name": extracted_name,
            "dob": extracted_dob,
            "id_number": extracted_id,
            "timestamp": datetime.utcnow().isoformat()
        }

        self.add_kyc_record(kyc_hash, record)
        storage.save_json(f"kyc_{kyc_hash}.json", record)

        return {
            "success": True,
            "verified": True,
            "kyc_hash": kyc_hash,
            "message": "KYC verified successfully",
            "data": record
        }

    # ======================================================
    # Validation utilities
    # ======================================================
    def verify_name_match(self, a: str, b: Optional[str], threshold: float = 0.80) -> bool:
        if not a or not b:
            return False

        a = self._normalize_name(a)
        b = self._normalize_name(b)

        if a == b:
            return True

        return SequenceMatcher(None, a, b).ratio() >= threshold

    def verify_age(self, dob_str: Optional[str]) -> bool:
        if not dob_str:
            return False

        dob = self._parse_date_string(dob_str)
        if not dob:
            return False

        today = date.today()
        age = today.year - dob.year - (
            (today.month, today.day) < (dob.month, dob.day)
        )
        return age >= settings.MIN_AGE

    # ======================================================
    # Helpers → parsing + normalizing
    # ======================================================
    def _normalize_name(self, name: str) -> str:
        cleaned = "".join(ch for ch in name if ch.isalnum() or ch.isspace())
        return " ".join(cleaned.lower().split())

    def _parse_date_string(self, s: str) -> Optional[date]:
        from datetime import datetime
        formats = [
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%b %d %Y",
            "%d %b %Y"
        ]
        for fmt in formats:
            try:
                return datetime.strptime(s, fmt).date()
            except:
                pass
        return None

    # ======================================================
    # Face matching
    # ======================================================
    def _compare_faces(self, id_bytes: bytes, selfie_bytes: bytes) -> bool:
        def prep(b):
            arr = np.frombuffer(b, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
            img = cv2.resize(img, (128, 128))
            return img.astype("float32") / 255.0

        try:
            a = prep(id_bytes)
            b = prep(selfie_bytes)
            diff = np.linalg.norm(a - b)
            return diff < 15.0
        except:
            return False
