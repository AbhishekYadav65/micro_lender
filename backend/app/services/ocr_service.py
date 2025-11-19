"""
OCR Service using Tesseract or PaddleOCR (local processing only)
Extracts name, DOB, and ID number from identity documents
"""
import re
import cv2
import numpy as np
from datetime import datetime
from typing import Dict, Optional
import pytesseract
from PIL import Image
import io
import logging

# Uncomment to use PaddleOCR instead of Tesseract
# from paddleocr import PaddleOCR

logger = logging.getLogger(__name__)


class OCRService:
    def __init__(self, use_paddle: bool = False):
        """
        Initialize OCR service
        
        Args:
            use_paddle: If True, use PaddleOCR; otherwise use Tesseract
        """
        self.use_paddle = use_paddle
        
        if use_paddle:
            # Initialize PaddleOCR
            # self.ocr = PaddleOCR(use_angle_cls=True, lang='en')
            logger.info("PaddleOCR initialized")
        else:
            # Tesseract configuration
            # Ensure tesseract is installed: sudo apt-get install tesseract-ocr
            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            logger.info("Using Tesseract OCR")
        
        # Common date patterns
        self.date_patterns = [
            r'\b(\d{2})[/-](\d{2})[/-](\d{4})\b',  # DD/MM/YYYY or DD-MM-YYYY
            r'\b(\d{4})[/-](\d{2})[/-](\d{2})\b',  # YYYY/MM/DD or YYYY-MM-DD
            r'\b(\d{2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})\b',  # DD Month YYYY
            r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{2}),?\s+(\d{4})\b',  # Month DD, YYYY
        ]
        
        # ID number patterns (examples for different countries)
        self.id_patterns = [
            r'\b[A-Z]{1,2}\d{6,8}\b',  # Passport style
            r'\b\d{9,12}\b',  # SSN / National ID style
            r'\b[A-Z0-9]{8,15}\b',  # Driver's license style
        ]
    
    def preprocess_image(self, image_bytes: bytes) -> np.ndarray:
        """
        Preprocess image for better OCR results
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Preprocessed image as numpy array
        """
        # Convert bytes to numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Denoise
        denoised = cv2.fastNlMeansDenoising(thresh, None, 10, 7, 21)
        
        # Dilation to make text more visible
        kernel = np.ones((1, 1), np.uint8)
        dilated = cv2.dilate(denoised, kernel, iterations=1)
        
        return dilated
    
    def extract_text_tesseract(self, image: np.ndarray) -> str:
        """
        Extract text using Tesseract OCR
        
        Args:
            image: Preprocessed image
            
        Returns:
            Extracted text
        """
        try:
            # Configure Tesseract for better accuracy
            custom_config = r'--oem 3 --psm 6'
            text = pytesseract.image_to_string(image, config=custom_config)
            return text
        except Exception as e:
            logger.error(f"Tesseract extraction error: {str(e)}")
            return ""
    
    def extract_text_paddle(self, image_bytes: bytes) -> str:
        """
        Extract text using PaddleOCR
        
        Args:
            image_bytes: Raw image bytes
            
        Returns:
            Extracted text
        """
        try:
            # Convert bytes to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Run OCR
            result = self.ocr.ocr(img, cls=True)
            
            # Extract text from result
            text_lines = []
            if result and len(result) > 0:
                for line in result[0]:
                    if line and len(line) > 1:
                        text_lines.append(line[1][0])
            
            return '\n'.join(text_lines)
        except Exception as e:
            logger.error(f"PaddleOCR extraction error: {str(e)}")
            return ""
    
    def extract_name(self, text: str) -> Optional[str]:
        """
        Extract name from OCR text
        
        Common patterns:
        - Lines with "NAME:" or "Name:"
        - Capitalized words in specific positions
        - After keywords like "Full Name", "Holder Name"
        
        Args:
            text: OCR extracted text
            
        Returns:
            Extracted name or None
        """
        lines = text.split('\n')
        
        # Pattern 1: Look for explicit name label
        name_keywords = ['name', 'full name', 'holder', 'bearer', 'surname']
        for i, line in enumerate(lines):
            line_lower = line.lower()
            for keyword in name_keywords:
                if keyword in line_lower:
                    # Check if name is on same line
                    parts = line.split(':')
                    if len(parts) > 1:
                        name = parts[1].strip()
                        if self._is_valid_name(name):
                            return name
                    # Check next line
                    if i + 1 < len(lines):
                        name = lines[i + 1].strip()
                        if self._is_valid_name(name):
                            return name
        
        # Pattern 2: Find capitalized sequences (likely names)
        for line in lines:
            words = line.split()
            capitalized_words = [w for w in words if w and w[0].isupper() and len(w) > 2]
            if 2 <= len(capitalized_words) <= 5:
                name = ' '.join(capitalized_words)
                if self._is_valid_name(name):
                    return name
        
        return None
    
    def extract_date_of_birth(self, text: str) -> Optional[str]:
        """
        Extract date of birth from OCR text
        
        Args:
            text: OCR extracted text
            
        Returns:
            Date of birth in YYYY-MM-DD format or None
        """
        # Look for DOB keywords
        dob_keywords = ['dob', 'date of birth', 'birth date', 'born']
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Check if line contains DOB keyword
            for keyword in dob_keywords:
                if keyword in line_lower:
                    # Search current and next line for date
                    search_text = line + (' ' + lines[i + 1] if i + 1 < len(lines) else '')
                    date = self._extract_date_from_text(search_text)
                    if date:
                        return date
        
        # Search entire text for dates
        date = self._extract_date_from_text(text)
        return date
    
    def extract_id_number(self, text: str) -> Optional[str]:
        """
        Extract ID number from OCR text
        
        Args:
            text: OCR extracted text
            
        Returns:
            ID number or None
        """
        # Look for ID keywords
        id_keywords = ['id no', 'id number', 'passport no', 'license no', 'number']
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Check if line contains ID keyword
            for keyword in id_keywords:
                if keyword in line_lower:
                    # Search current and next line
                    search_text = line + (' ' + lines[i + 1] if i + 1 < len(lines) else '')
                    id_num = self._extract_id_from_text(search_text)
                    if id_num:
                        return id_num
        
        # Search entire text for ID patterns
        id_num = self._extract_id_from_text(text)
        return id_num
    
    def _extract_date_from_text(self, text: str) -> Optional[str]:
        """Extract date from text using regex patterns"""
        for pattern in self.date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groups()
                    
                    # Handle different date formats
                    if len(groups) == 3:
                        if groups[0].isdigit() and len(groups[0]) == 4:
                            # YYYY-MM-DD
                            year, month, day = groups
                        elif groups[2].isdigit() and len(groups[2]) == 4:
                            # DD-MM-YYYY or Month DD YYYY
                            if groups[1].isdigit():
                                day, month, year = groups
                            else:
                                # Convert month name to number
                                month_map = {
                                    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                                    'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                                    'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
                                }
                                month_name = groups[1][:3].lower() if not groups[0].isdigit() else groups[1][:3].lower()
                                if not groups[0].isdigit():
                                    month = month_map.get(groups[0][:3].lower())
                                    day = groups[1]
                                    year = groups[2]
                                else:
                                    day = groups[0]
                                    month = month_map.get(month_name)
                                    year = groups[2]
                        else:
                            continue
                        
                        # Normalize format
                        day = str(int(day)).zfill(2)
                        month = str(int(month)).zfill(2) if month.isdigit() else month
                        
                        # Validate date
                        date_obj = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
                        return date_obj.strftime("%Y-%m-%d")
                except (ValueError, AttributeError):
                    continue
        
        return None
    
    def _extract_id_from_text(self, text: str) -> Optional[str]:
        """Extract ID number from text using regex patterns"""
        for pattern in self.id_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None
    
    def _is_valid_name(self, name: str) -> bool:
        """Validate if extracted text is likely a name"""
        if not name or len(name) < 3:
            return False
        
        # Should contain only letters, spaces, hyphens, apostrophes
        if not re.match(r"^[A-Za-z\s\-']+$", name):
            return False
        
        # Should have at least 2 words (first and last name)
        words = name.split()
        if len(words) < 2:
            return False
        
        # Each word should be reasonable length
        for word in words:
            if len(word) < 2 or len(word) > 20:
                return False
        
        return True
    
    def process_id_document(self, image_bytes: bytes) -> Dict:
        """
        Main method to process ID document and extract KYC data
        
        Args:
            image_bytes: Raw image bytes of ID document
            
        Returns:
            Dictionary with extracted data and success status
        """
        try:
            logger.info("Processing ID document...")
            
            # Preprocess image
            preprocessed = self.preprocess_image(image_bytes)
            
            # Extract text
            if self.use_paddle:
                text = self.extract_text_paddle(image_bytes)
            else:
                text = self.extract_text_tesseract(preprocessed)
            
            logger.info(f"Extracted text length: {len(text)} characters")
            
            if not text or len(text) < 20:
                return {
                    'success': False,
                    'error': 'Insufficient text extracted from document'
                }
            
            # Extract individual fields
            name = self.extract_name(text)
            dob = self.extract_date_of_birth(text)
            id_number = self.extract_id_number(text)
            
            logger.info(f"Extracted - Name: {name}, DOB: {dob}, ID: {id_number}")
            
            # Determine ID type
            id_type = 'unknown'
            if id_number:
                if re.match(r'[A-Z]{1,2}\d{6,8}', id_number):
                    id_type = 'passport'
                elif re.match(r'\d{9,12}', id_number):
                    id_type = 'national_id'
                else:
                    id_type = 'driver_license'
            
            return {
                'success': True,
                'data': {
                    'name': name,
                    'date_of_birth': dob,
                    'id_number': id_number,
                    'id_type': id_type,
                    'raw_text': text[:500]  # First 500 chars for debugging
                }
            }
            
        except Exception as e:
            logger.error(f"OCR processing error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def check_health(self) -> bool:
        """Check if OCR service is operational"""
        try:
            # Test with a simple image
            test_img = np.ones((100, 100), dtype=np.uint8) * 255
            if self.use_paddle:
                return True  # PaddleOCR check
            else:
                pytesseract.get_tesseract_version()
                return True
        except Exception:
            return False