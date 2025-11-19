from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.kyc_service import KYCService

router = APIRouter(prefix="/api/kyc", tags=["KYC"])
kyc_service = KYCService()


@router.post("/submit")
async def submit_kyc(
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    id_document: UploadFile = File(...),
    selfie: UploadFile = File(...),
):
    print("=== DEBUG: KYC Upload ===")
    print("ID filename:", id_document.filename)
    print("ID content_type:", id_document.content_type)
    print("Selfie filename:", selfie.filename)
    print("Selfie content_type:", selfie.content_type)
    print("=========================")

    allowed_types = {"image/png", "image/jpeg"}

    if id_document.content_type not in allowed_types:
        raise HTTPException(400, "ID document must be an image")

    if selfie.content_type not in allowed_types:
        raise HTTPException(400, "Selfie must be an image")

    id_bytes = await id_document.read()
    selfie_bytes = await selfie.read()

    result = await kyc_service.verify_kyc(
        full_name=full_name,
        email=email,
        phone=phone,
        id_document_bytes=id_bytes,
        selfie_bytes=selfie_bytes
    )

    return result
