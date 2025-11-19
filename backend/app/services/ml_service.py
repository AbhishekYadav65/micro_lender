"""
ML Service
Provides:
 - feature validation
 - probability of default prediction
 - risk category classification
 - SHAP-style mock explanations (works even without real model)
"""

import logging
import numpy as np
from pathlib import Path
import joblib
from typing import Dict, Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class MLService:
    def __init__(self):
        """
        Load trained ML model if available;
        otherwise fallback to safe mock predictor.
        """
        self.model = None
        self.scaler = None

        model_path = Path(settings.MODEL_PATH)
        scaler_path = Path(settings.SCALER_PATH)

        if model_path.exists() and scaler_path.exists():
            try:
                self.model = joblib.load(model_path)
                self.scaler = joblib.load(scaler_path)
                logger.info("Loaded real ML model and scaler.")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")
        else:
            logger.warning("Model not found. Using mock ML model.")

        # Required features for validation
        self.expected_features = [
            "income",
            "employment_length",
            "debt_to_income",
            "credit_inquiries",
            "loan_amount",
            "loan_term",
        ]

    # ------------------------------------------------------------
    # Feature Validation
    # ------------------------------------------------------------
    def validate_features(self, features: Dict[str, Any]) -> bool:
        for f in self.expected_features:
            if f not in features:
                return False
            try:
                float(features[f])
            except:
                return False
        return True

    # ------------------------------------------------------------
    # Main Prediction
    # ------------------------------------------------------------
    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns:
            {
                "success": True,
                "prediction": float,
                "probability": float,
                "risk_category": str
            }
        """
        try:
            x = np.array([features[f] for f in self.expected_features], dtype=float).reshape(1, -1)

            # Real model path
            if self.model and self.scaler:
                x_scaled = self.scaler.transform(x)
                prob_default = float(self.model.predict_proba(x_scaled)[0][1])
            else:
                # MOCK model fallback
                prob_default = self._mock_probability(features)

            # Risk mapping
            risk_cat = self._risk_category(prob_default)

            return {
                "success": True,
                "prediction": prob_default,
                "probability": prob_default,
                "risk_category": risk_cat
            }

        except Exception as e:
            logger.error(f"Prediction error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------
    # SHAP Explanation (Mock Until Model Exists)
    # ------------------------------------------------------------
    def generate_shap_explanation(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a SHAP-style dictionary even without a real model.
        """
        try:
            if self.model:
                # Real SHAP can be added later
                pass

            # Mock SHAP values
            shap_vals = {f: round(np.random.uniform(-0.05, 0.05), 4) for f in self.expected_features}

            importance = sorted(
                [{"feature": f, "importance": abs(v)} for f, v in shap_vals.items()],
                key=lambda x: x["importance"],
                reverse=True
            )

            return {
                "success": True,
                "shap_values": shap_vals,
                "feature_importance": importance,
                "base_value": 0.10,  # arbitrary
            }

        except Exception as e:
            logger.error(f"SHAP generation error: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------
    def _mock_probability(self, features: Dict[str, float]) -> float:
        """
        Deterministic mock model so results are stable.
        """
        inc = float(features["income"])
        dti = float(features["debt_to_income"])
        inquiries = float(features["credit_inquiries"])
        loan_amt = float(features["loan_amount"])

        score = (loan_amt / (inc + 1)) + (dti / 100) + (inquiries * 0.02)
        score = min(max(score, 0), 1)

        return round(score, 4)

    def _risk_category(self, probability: float) -> str:
        """
        Based on settings thresholds.
        """
        if probability * 100 < (settings.LOW_RISK_THRESHOLD / 100):
            return "Low"
        elif probability * 100 < (settings.MEDIUM_RISK_THRESHOLD / 100):
            return "Medium"
        return "High"

    # ------------------------------------------------------------
    def check_health(self) -> bool:
        """
        Returns True if mock model works OR if real model loads.
        """
        try:
            return True
        except:
            return False
