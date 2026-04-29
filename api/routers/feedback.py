"""
医生反馈接口
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackRequest(BaseModel):
    patient_id: str
    diagnosis_correct: Optional[bool] = None
    comments: Optional[str] = None
    follow_up_result: Optional[str] = None


@router.post("/")
async def submit_feedback(request: FeedbackRequest):
    """提交诊断反馈"""
    return {"success": True, "message": "反馈已记录"}
