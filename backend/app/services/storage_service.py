"""
Storage Service for KYC documents and ML explanations
Supports local file system, IPFS, and S3
"""
import os
import json
import hashlib
from typing import Dict, Optional
from pathlib import Path
import logging

# Optional imports
try:
    import ipfshttpclient
    IPFS_AVAILABLE = True
except ImportError:
    IPFS_AVAILABLE = False

try:
    import boto3
    from botocore.exceptions import ClientError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self, storage_type: str = 'local'):
        """
        Initialize storage service
        
        Args:
            storage_type: 'local', 'ipfs', or 's3'
        """
        self.storage_type = storage_type
        self.base_path = os.getenv('STORAGE_PATH', 'storage')
        
        # Create storage directories
        self.kyc_path = Path(self.base_path) / 'kyc_documents'
        self.explanation_path = Path(self.base_path) / 'explanations'
        
        self.kyc_path.mkdir(parents=True, exist_ok=True)
        self.explanation_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize storage backend
        self.ipfs_client = None
        self.s3_client = None
        
        if storage_type == 'ipfs' and IPFS_AVAILABLE:
            self._init_ipfs()
        elif storage_type == 's3' and S3_AVAILABLE:
            self._init_s3()
        
        logger.info(f"Storage service initialized: {storage_type}")
    
    def _init_ipfs(self):
        """Initialize IPFS client"""
        try:
            ipfs_addr = os.getenv('IPFS_ADDR', '/ip4/127.0.0.1/tcp/5001')
            self.ipfs_client = ipfshttpclient.connect(ipfs_addr)
            logger.info("IPFS client connected")
        except Exception as e:
            logger.error(f"IPFS connection failed: {str(e)}")
            logger.info("Falling back to local storage")
            self.storage_type = 'local'
    
    def _init_s3(self):
        """Initialize S3 client"""
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION', 'us-east-1')
            )
            self.bucket_name = os.getenv('S3_BUCKET_NAME')
            logger.info(f"S3 client initialized for bucket: {self.bucket_name}")
        except Exception as e:
            logger.error(f"S3 initialization failed: {str(e)}")
            logger.info("Falling back to local storage")
            self.storage_type = 'local'
    
    def store_kyc_documents(
        self,
        kyc_hash: str,
        id_document: bytes,
        selfie: bytes,
        kyc_data: Dict
    ) -> Dict:
        """
        Store KYC documents and data
        
        Args:
            kyc_hash: SHA256 hash of KYC data
            id_document: ID document image bytes
            selfie: Selfie image bytes
            kyc_data: KYC data dictionary
            
        Returns:
            Storage result with URLs/CIDs
        """
        try:
            # Create directory for this KYC submission
            kyc_dir = self.kyc_path / kyc_hash
            kyc_dir.mkdir(exist_ok=True)
            
            # Save files locally (always as backup)
            id_doc_path = kyc_dir / 'id_document.jpg'
            selfie_path = kyc_dir / 'selfie.jpg'
            data_path = kyc_dir / 'kyc_data.json'
            
            with open(id_doc_path, 'wb') as f:
                f.write(id_document)
            
            with open(selfie_path, 'wb') as f:
                f.write(selfie)
            
            with open(data_path, 'w') as f:
                json.dump(kyc_data, f, indent=2)
            
            logger.info(f"KYC documents stored locally: {kyc_dir}")
            
            # Store on selected backend
            urls = {
                'id_document': str(id_doc_path),
                'selfie': str(selfie_path),
                'kyc_data': str(data_path)
            }
            
            if self.storage_type == 'ipfs' and self.ipfs_client:
                ipfs_result = self._store_on_ipfs(kyc_dir)
                if ipfs_result:
                    urls.update(ipfs_result)
            
            elif self.storage_type == 's3' and self.s3_client:
                s3_result = self._store_on_s3(
                    kyc_hash,
                    id_document,
                    selfie,
                    kyc_data
                )
                if s3_result:
                    urls.update(s3_result)
            
            return {
                'success': True,
                'storage_type': self.storage_type,
                'url': urls.get('kyc_data', str(data_path)),
                'urls': urls
            }
            
        except Exception as e:
            logger.error(f"Storage error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def store_explanation(
        self,
        explanation_hash: str,
        explanation_data: Dict
    ) -> Dict:
        """
        Store ML explanation data
        
        Args:
            explanation_hash: SHA256 hash of explanation
            explanation_data: Explanation dictionary
            
        Returns:
            Storage result
        """
        try:
            # Save locally
            file_path = self.explanation_path / f"{explanation_hash}.json"
            
            with open(file_path, 'w') as f:
                json.dump(explanation_data, f, indent=2)
            
            logger.info(f"Explanation stored: {file_path}")
            
            url = str(file_path)
            
            # Store on selected backend
            if self.storage_type == 'ipfs' and self.ipfs_client:
                ipfs_cid = self._add_to_ipfs(json.dumps(explanation_data))
                if ipfs_cid:
                    url = f"ipfs://{ipfs_cid}"
            
            elif self.storage_type == 's3' and self.s3_client:
                s3_url = self._upload_to_s3(
                    f"explanations/{explanation_hash}.json",
                    json.dumps(explanation_data).encode()
                )
                if s3_url:
                    url = s3_url
            
            return {
                'success': True,
                'storage_type': self.storage_type,
                'url': url,
                'hash': explanation_hash
            }
            
        except Exception as e:
            logger.error(f"Explanation storage error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def retrieve_explanation(self, explanation_hash: str) -> Optional[Dict]:
        """Retrieve explanation by hash"""
        try:
            file_path = self.explanation_path / f"{explanation_hash}.json"
            
            if file_path.exists():
                with open(file_path, 'r') as f:
                    return json.load(f)
            
            # Try other storage backends if local not found
            if self.storage_type == 's3' and self.s3_client:
                return self._retrieve_from_s3(f"explanations/{explanation_hash}.json")
            
            return None
            
        except Exception as e:
            logger.error(f"Retrieve explanation error: {str(e)}")
            return None
    
    def explanation_exists(self, explanation_hash: str) -> bool:
        """Check if explanation exists"""
        file_path = self.explanation_path / f"{explanation_hash}.json"
        return file_path.exists()
    
    def _store_on_ipfs(self, directory: Path) -> Optional[Dict]:
        """Store directory on IPFS"""
        try:
            result = self.ipfs_client.add(str(directory), recursive=True)
            
            # Get the directory CID (last item)
            if isinstance(result, list):
                dir_cid = result[-1]['Hash']
            else:
                dir_cid = result['Hash']
            
            logger.info(f"Stored on IPFS: {dir_cid}")
            
            return {
                'ipfs_cid': dir_cid,
                'ipfs_url': f"ipfs://{dir_cid}"
            }
            
        except Exception as e:
            logger.error(f"IPFS storage error: {str(e)}")
            return None
    
    def _add_to_ipfs(self, content: str) -> Optional[str]:
        """Add content to IPFS"""
        try:
            result = self.ipfs_client.add_str(content)
            logger.info(f"Added to IPFS: {result}")
            return result
        except Exception as e:
            logger.error(f"IPFS add error: {str(e)}")
            return None
    
    def _store_on_s3(
        self,
        kyc_hash: str,
        id_document: bytes,
        selfie: bytes,
        kyc_data: Dict
    ) -> Optional[Dict]:
        """Store on S3"""
        try:
            prefix = f"kyc/{kyc_hash}/"
            
            # Upload files
            id_url = self._upload_to_s3(f"{prefix}id_document.jpg", id_document)
            selfie_url = self._upload_to_s3(f"{prefix}selfie.jpg", selfie)
            data_url = self._upload_to_s3(
                f"{prefix}kyc_data.json",
                json.dumps(kyc_data).encode()
            )
            
            return {
                'id_document': id_url,
                'selfie': selfie_url,
                'kyc_data': data_url
            }
            
        except Exception as e:
            logger.error(f"S3 storage error: {str(e)}")
            return None
    
    def _upload_to_s3(self, key: str, data: bytes) -> Optional[str]:
        """Upload data to S3"""
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=data
            )
            
            url = f"s3://{self.bucket_name}/{key}"
            logger.info(f"Uploaded to S3: {url}")
            return url
            
        except ClientError as e:
            logger.error(f"S3 upload error: {str(e)}")
            return None
    
    def _retrieve_from_s3(self, key: str) -> Optional[Dict]:
        """Retrieve data from S3"""
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            data = response['Body'].read()
            return json.loads(data.decode())
            
        except ClientError as e:
            logger.error(f"S3 retrieve error: {str(e)}")
            return None
    
    def check_health(self) -> bool:
        """Check storage service health"""
        try:
            # Check local storage
            if not self.kyc_path.exists() or not self.explanation_path.exists():
                return False
            
            # Check IPFS connection
            if self.storage_type == 'ipfs' and self.ipfs_client:
                self.ipfs_client.id()
            
            # Check S3 connection
            if self.storage_type == 's3' and self.s3_client:
                self.s3_client.list_buckets()
            
            return True
            
        except Exception:
            return False