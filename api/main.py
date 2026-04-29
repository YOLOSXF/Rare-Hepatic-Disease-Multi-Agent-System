"""
Medical-Agent API 服务入口
FastAPI 应用 (v3.0 - LangGraph StateGraph 架构)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from contextlib import asynccontextmanager

from .schemas import HealthStatus
from .routers.diagnosis import router as diagnosis_router
from .routers.hitl import router as hitl_router
from .routers.feedback import router as feedback_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Starting Medical-Agent API (LangGraph v3 - StateGraph)...")
    yield
    logger.info("Medical-Agent API shutting down")


app = FastAPI(
    title="Medical-Agent API",
    description="基于多智能体对抗推理的肝病辅助诊断系统（LangGraph StateGraph 架构）",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由模块
app.include_router(diagnosis_router, prefix="/api/v1")
app.include_router(hitl_router, prefix="/api/v1")
app.include_router(feedback_router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    """根路径"""
    return {
        "name": "Medical-Agent API",
        "version": "3.0.0",
        "architecture": "LangGraph StateGraph",
        "status": "running",
        "features": [
            "MDT Multi-Agent Debate",
            "Falsification Engine with conditional back-edge",
            "HITL Interrupt/Resume via langgraph.types.interrupt",
            "Guideline Verification with conditional rollback",
            "EWAS Graph Update",
            "MemorySaver checkpoint persistence",
        ],
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthStatus, tags=["Health"])
async def health_check():
    """健康检查"""
    return HealthStatus(
        status="healthy",
        components={
            "diagnosis_router": "ready",
            "hitl_router": "ready",
            "feedback_router": "ready",
            "langgraph_stategraph": "ready",
        }
    )
