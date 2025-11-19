from fastapi import APIRouter, HTTPException
from app.services.ml_service import MLService
from app.models.schemas import ScoreRequest, ScoreResponse
import hashlib
import json
from pathlib import Path

router = APIRouter(prefix="/api/score", tags=["ML"])
ml_service = MLService()


@router.post("/predict", response_model=ScoreResponse)
async def predict_score(request: ScoreRequest):
    VALID = ml_service.validate_features(request.features)
    if not VALID:
        raise HTTPException(status_code=400, detail="Invalid feature set")

    result = ml_service.predict(request.features)

    prob = result["probability"]
    prob_bp = int(prob * 10000)
    risk = result["risk_category"]

    shap = ml_service.generate_shap_explanation(request.features)

    exp_json = json.dumps(shap)
    exp_hash = "0x" + hashlib.sha256(exp_json.encode()).hexdigest()

    path = Path("storage/explanations")
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / f"{exp_hash}.json"
    file_path.write_text(exp_json)

    return {
        "success": True,
        "probability_of_default": prob_bp,
        "risk_category": risk,
        "explanation_hash": exp_hash,
        "shap_summary": shap,
        "storage_url": str(file_path)
    }
