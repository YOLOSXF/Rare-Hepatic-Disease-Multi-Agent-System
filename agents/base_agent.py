"""
Agent 基类
定义所有智能体的通用接口和能力
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import asyncio
from loguru import logger


class AgentConfig(BaseModel):
    """Agent 配置"""
    name: str
    enabled: bool = True
    timeout_seconds: int = 60
    max_retries: int = 3
    temperature: float = 0.1


class AgentResponse(BaseModel):
    """Agent 响应基类"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}
    execution_time_ms: Optional[int] = None


class BaseAgent(ABC):
    """
    智能体基类
    
    所有专科 Agent 都继承自此类，实现统一的接口
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        """
        初始化 Agent
        
        Args:
            config: Agent 配置
        """
        self.config = config or AgentConfig(name=self.__class__.__name__)
        self._initialized = False
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称"""
        pass
    
    @abstractmethod
    async def execute(self, input_data: Dict[str, Any]) -> AgentResponse:
        """
        执行 Agent 任务
        
        Args:
            input_data: 输入数据
        
        Returns:
            AgentResponse: 执行结果
        """
        pass
    
    async def initialize(self) -> bool:
        """
        初始化 Agent（加载模型、数据库等）
        
        Returns:
            bool: 是否初始化成功
        """
        if self._initialized:
            return True
        
        try:
            await self._load_resources()
            self._initialized = True
            logger.info(f"Agent {self.name} initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Agent {self.name}: {e}")
            return False
    
    async def _load_resources(self):
        """加载资源（子类实现）"""
        pass
    
    async def _retry_execute(self, input_data: Dict[str, Any]) -> AgentResponse:
        """
        带重试的执行
        
        Args:
            input_data: 输入数据
        
        Returns:
            AgentResponse: 执行结果
        """
        import time
        from tenacity import retry, stop_after_attempt, wait_exponential
        
        @retry(
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(multiplier=1, min=4, max=10)
        )
        async def _execute_with_retry():
            start_time = time.time()
            try:
                result = await self.execute(input_data)
                result.execution_time_ms = int((time.time() - start_time) * 1000)
                return result
            except Exception as e:
                logger.error(f"Agent {self.name} execution failed: {e}")
                raise
        
        try:
            return await _execute_with_retry()
        except Exception as e:
            return AgentResponse(
                success=False,
                error=str(e),
                metadata={"agent": self.name}
            )
    
    def _create_response(
        self,
        success: bool,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentResponse:
        """
        创建标准响应
        
        Args:
            success: 是否成功
            data: 响应数据
            error: 错误信息
            metadata: 元数据
        
        Returns:
            AgentResponse: 响应对象
        """
        return AgentResponse(
            success=success,
            data=data,
            error=error,
            metadata={
                "agent": self.name,
                **(metadata or {})
            }
        )
    
    async def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            bool: 是否健康
        """
        return self._initialized
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        获取 Agent 能力描述
        
        Returns:
            能力描述字典
        """
        return {
            "name": self.name,
            "enabled": self.config.enabled,
            "timeout_seconds": self.config.timeout_seconds,
            "description": self.__doc__ or ""
        }
