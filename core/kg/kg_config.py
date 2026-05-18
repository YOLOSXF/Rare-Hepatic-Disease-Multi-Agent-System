"""
知识图谱配置加载

职责：
1. 从config.yaml加载knowledge_graph配置段
2. 提供KG各组件的统一配置访问
3. 支持Feature Flag控制KG功能开关
4. 提供Neo4j/Milvus连接参数

使用示例：
    from core.kg.kg_config import KGConfig
    config = KGConfig.from_yaml()
    if config.enabled:
        driver = config.get_neo4j_driver()
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


@dataclass
class Neo4jConfig:
    url: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "12345678"
    database: str = "neo4j"

    def get_driver(self):
        from neo4j import GraphDatabase
        return GraphDatabase.driver(
            self.url,
            auth=(self.username, self.password),
        )


@dataclass
class MilvusConfig:
    host: str = "localhost"
    port: int = 19530
    collection_name: str = "kg_entities"
    alias: str = "default"

    def get_client(self):
        from pymilvus import MilvusClient
        return MilvusClient(
            uri=f"http://{self.host}:{self.port}"
        )


@dataclass
class EmbeddingConfig:
    model_name: str = "BAAI/bge-m3"
    model_path: Optional[str] = None
    dim: int = 1024
    batch_size: int = 32

    def get_model_path(self) -> str:
        if self.model_path and Path(self.model_path).exists():
            return self.model_path
        project_root = Path(__file__).parent.parent.parent
        local_path = project_root / "model" / "Xorbits" / "bge-m3"
        if local_path.exists():
            return str(local_path)
        return self.model_name


@dataclass
class ActivationConfig:
    similarity_threshold: float = 0.5
    top_k_diseases: int = 5
    core_feature_weight: float = 2.0
    supporting_feature_weight: float = 1.0


@dataclass
class IntegrationConfig:
    falsification: bool = False
    guideline_verify: bool = False
    info_gap: bool = False
    debate_context: bool = False


@dataclass
class KGConfig:
    enabled: bool = False
    engine: str = "networkx"
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    milvus: MilvusConfig = field(default_factory=MilvusConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    activation: ActivationConfig = field(default_factory=ActivationConfig)
    integration: IntegrationConfig = field(default_factory=IntegrationConfig)

    def get_neo4j_driver(self):
        return self.neo4j.get_driver()

    def get_milvus_client(self):
        return self.milvus.get_client()

    def get_embedding_model(self):
        from sentence_transformers import SentenceTransformer
        model_path = self.embedding.get_model_path()
        return SentenceTransformer(model_path)

    def _auto_detect_engine(self) -> None:
        try:
            driver = self.neo4j.get_driver()
            with driver.session(database=self.neo4j.database) as session:
                session.run("RETURN 1")
            driver.close()
            self.engine = "neo4j"
            logger.info("Auto-detected Neo4j available, engine=neo4j")
        except Exception:
            self.engine = "networkx"
            logger.info("Neo4j not available, engine=networkx")

    @classmethod
    def from_yaml(cls, config_path: Optional[str] = None) -> "KGConfig":
        if config_path is None:
            project_root = Path(__file__).parent.parent.parent
            config_path = str(project_root / "config.yaml")

        if not Path(config_path).exists():
            logger.warning(f"Config file not found: {config_path}, using defaults")
            config = cls()
            config._auto_detect_engine()
            return config

        if not YAML_AVAILABLE:
            logger.warning("PyYAML not installed, using default KG config")
            config = cls()
            config._auto_detect_engine()
            return config

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                full_config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            config = cls()
            config._auto_detect_engine()
            return config

        kg_raw = full_config.get("knowledge_graph", {})
        if not kg_raw:
            logger.info("No knowledge_graph section in config, using defaults")
            config = cls()
            config._auto_detect_engine()
            return config

        neo4j_raw = kg_raw.get("neo4j", {})
        neo4j_cfg = Neo4jConfig(
            url=neo4j_raw.get("url", "bolt://localhost:7687"),
            username=neo4j_raw.get("username", "neo4j"),
            password=neo4j_raw.get("password", os.environ.get("NEO4J_PASSWORD", "12345678")),
            database=neo4j_raw.get("database", "neo4j"),
        )

        milvus_raw = kg_raw.get("milvus", {})
        milvus_cfg = MilvusConfig(
            host=milvus_raw.get("host", "localhost"),
            port=milvus_raw.get("port", 19530),
            collection_name=milvus_raw.get("collection_name", "kg_entities"),
            alias=milvus_raw.get("alias", "default"),
        )

        embedding_raw = kg_raw.get("embedding", {})
        project_root = Path(__file__).parent.parent.parent
        default_model_path = str(project_root / "model" / "Xorbits" / "bge-m3")
        embedding_cfg = EmbeddingConfig(
            model_name=kg_raw.get("embedding_model", "BAAI/bge-m3"),
            model_path=embedding_raw.get("model_path", default_model_path),
            dim=kg_raw.get("embedding_dim", 1024),
            batch_size=embedding_raw.get("batch_size", 32),
        )

        activation_raw = kg_raw.get("activation", {})
        activation_cfg = ActivationConfig(
            similarity_threshold=activation_raw.get("similarity_threshold", 0.5),
            top_k_diseases=activation_raw.get("top_k_diseases", 5),
            core_feature_weight=activation_raw.get("core_feature_weight", 2.0),
            supporting_feature_weight=activation_raw.get("supporting_feature_weight", 1.0),
        )

        integration_raw = kg_raw.get("integration", {})
        integration_cfg = IntegrationConfig(
            falsification=integration_raw.get("falsification", False),
            guideline_verify=integration_raw.get("guideline_verify", False),
            info_gap=integration_raw.get("info_gap", False),
            debate_context=integration_raw.get("debate_context", False),
        )

        config = cls(
            enabled=kg_raw.get("enabled", False),
            engine=kg_raw.get("engine", ""),
            neo4j=neo4j_cfg,
            milvus=milvus_cfg,
            embedding=embedding_cfg,
            activation=activation_cfg,
            integration=integration_cfg,
        )

        if not config.engine or config.engine == "networkx":
            config._auto_detect_engine()

        logger.info(
            f"KG config loaded: enabled={config.enabled}, engine={config.engine}, "
            f"neo4j={config.neo4j.url}, milvus={config.milvus.host}:{config.milvus.port}"
        )
        return config
