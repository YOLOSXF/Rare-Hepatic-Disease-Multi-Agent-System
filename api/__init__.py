"""
Medical-Agent API 模块
"""

from .schemas import PatientInput, DiagnosisResponse, HealthStatus, ScreeningResult

__all__ = [
    "PatientInput",
    "DiagnosisResponse",
    "HealthStatus",
    "ScreeningResult",
]
