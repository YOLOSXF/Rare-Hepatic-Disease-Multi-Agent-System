"""
LLM 客户端管理模块

职责：
1. 从 .env 环境变量或 config.yaml 加载 LLM 配置
2. 创建并缓存 LangChain ChatOpenAI 客户端实例
3. 提供统一的客户端获取接口

配置优先级：.env 环境变量 > config.yaml 配置 > 默认值

环境变量说明：
- DASHSCOPE_API_KEY: DashScope API 密钥
- DASHSCOPE_MODEL: DashScope 模型名称
- DASHSCOPE_TEMPERATURE: 温度参数
- DASHSCOPE_MAX_TOKENS: 最大 token 数
- DASHSCOPE_API_BASE: API 基础 URL（可选）

使用示例：
    from core.llm_client import get_llm_client
    
    # 获取默认客户端
    client = get_llm_client()
    
    # 获取特定配置的客户端
    client = get_llm_client(temperature=0.2, max_tokens=3000)
    
    # 重置客户端缓存
    reset_llm_client()
"""

import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
from loguru import logger
from dotenv import load_dotenv

# 加载 .env 环境变量
load_dotenv()

# 全局客户端缓存
_llm_client_cache: Dict[str, Any] = {}


def load_llm_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    加载 LLM 配置

    优先级：.env 环境变量 > config.yaml 配置 > 默认值

    Args:
        config_path: 配置文件路径

    Returns:
        包含 LLM 配置的字典
    """
    config = {}

    # 1. 从 .env 环境变量读取
    env_config = {
        "api_key": os.getenv("DASHSCOPE_API_KEY"),
        "model": os.getenv("DASHSCOPE_MODEL"),
        "api_base": os.getenv("DASHSCOPE_API_BASE"),
        "temperature": os.getenv("DASHSCOPE_TEMPERATURE"),
        "max_tokens": os.getenv("DASHSCOPE_MAX_TOKENS"),
    }
    # 过滤掉 None 值
    config = {k: v for k, v in env_config.items() if v is not None}

    # 2. 从 config.yaml 读取（作为回退）
    try:
        yaml_path = Path(config_path)
        if yaml_path.exists():
            with open(yaml_path, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f) or {}

            llm_section = yaml_data.get('llm', {})
            if llm_section:
                # 只在环境变量未设置时使用 yaml 配置
                if "api_key" not in config:
                    api_key = llm_section.get('api_key') or os.getenv("OPENAI_API_KEY")
                    if api_key:
                        config["api_key"] = api_key
                if "model" not in config:
                    model = llm_section.get('model') or os.getenv("OPENAI_MODEL")
                    if model:
                        config["model"] = model
                if "api_base" not in config:
                    api_base = llm_section.get('api_base') or os.getenv("OPENAI_API_BASE")
                    if api_base:
                        config["api_base"] = api_base
                if "temperature" not in config:
                    config["temperature"] = str(llm_section.get('temperature', 0.1))
                if "max_tokens" not in config:
                    config["max_tokens"] = str(llm_section.get('max_tokens', 2000))
                if "timeout" not in config:
                    config["timeout"] = str(llm_section.get('timeout', 60))
    except Exception as e:
        logger.warning(f"Failed to load config.yaml, using env vars only: {e}")

    # 3. 应用默认值
    if "api_key" not in config:
        logger.error("No API key found. Please set DASHSCOPE_API_KEY or OPENAI_API_KEY in .env file.")
    if "model" not in config:
        config["model"] = "qwen-turbo"
    if "api_base" not in config:
        config["api_base"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    if "temperature" not in config:
        config["temperature"] = "0.1"
    if "max_tokens" not in config:
        config["max_tokens"] = "2000"
    if "timeout" not in config:
        config["timeout"] = "60"

    return config


def create_llm_client(
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    config_path: str = "config.yaml"
) -> Any:
    """
    创建 LangChain ChatOpenAI 客户端

    Args:
        temperature: 温度参数（可选，覆盖配置文件中的值）
        max_tokens: 最大 token 数（可选，覆盖配置文件中的值）
        config_path: 配置文件路径

    Returns:
        ChatOpenAI 实例
    """
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.error("langchain-openai not installed. Install with: pip install langchain-openai")
        raise ImportError(
            "langchain-openai is required for LLM integration. "
            "Install it with: pip install langchain-openai"
        )

    config = load_llm_config(config_path)

    if not config.get("api_key"):
        raise ValueError(
            "LLM API key not configured. Please set DASHSCOPE_API_KEY or OPENAI_API_KEY "
            "in your .env file or config.yaml."
        )

    # 构建客户端参数
    client_kwargs = {
        "api_key": config["api_key"],
        "model": config["model"],
        "base_url": config["api_base"],
        "temperature": float(temperature) if temperature is not None else float(config["temperature"]),
        "max_tokens": int(max_tokens) if max_tokens is not None else int(config["max_tokens"]),
    }

    # 添加超时配置
    try:
        client_kwargs["timeout"] = float(config.get("timeout", 60))
    except (ValueError, TypeError):
        pass

    logger.info(
        f"Creating LangChain ChatOpenAI client: "
        f"model={config['model']}, base_url={config['api_base']}"
    )

    try:
        client = ChatOpenAI(**client_kwargs)
        return client
    except Exception as e:
        logger.error(f"Failed to create ChatOpenAI client: {e}")
        raise


def get_llm_client(
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    config_path: str = "config.yaml"
) -> Any:
    """
    获取 LLM 客户端（带缓存）

    使用缓存避免重复创建客户端实例。如果 temperature 或 max_tokens
    与缓存的不同，会创建新的客户端。

    Args:
        temperature: 温度参数（可选，覆盖配置文件中的值）
        max_tokens: 最大 token 数（可选，覆盖配置文件中的值）
        config_path: 配置文件路径

    Returns:
        ChatOpenAI 实例
    """
    # 构建缓存键
    cache_key = f"{config_path}:{temperature}:{max_tokens}"

    if cache_key not in _llm_client_cache:
        _llm_client_cache[cache_key] = create_llm_client(
            temperature=temperature,
            max_tokens=max_tokens,
            config_path=config_path
        )
        logger.info(f"LLM client cached with key: {cache_key}")

    return _llm_client_cache[cache_key]


def reset_llm_client(config_path: Optional[str] = None):
    """
    重置 LLM 客户端缓存

    Args:
        config_path: 如果提供，只重置与该配置路径相关的缓存；
                     如果为 None，则重置所有缓存
    """
    if config_path is None:
        _llm_client_cache.clear()
        logger.info("All LLM client caches cleared")
    else:
        keys_to_remove = [k for k in _llm_client_cache.keys() if k.startswith(config_path)]
        for key in keys_to_remove:
            del _llm_client_cache[key]
        logger.info(f"Cleared {len(keys_to_remove)} LLM client cache entries for config: {config_path}")
