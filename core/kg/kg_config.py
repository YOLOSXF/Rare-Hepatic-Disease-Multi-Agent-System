"""
知识图谱配置加载

职责：
1. 从config.yaml加载knowledge_graph配置段
2. 提供KG各组件的统一配置访问
3. 支持Feature Flag控制KG功能开关
4. 提供Neo4j/Milvus连接参数
5. 加载领域配置（EL1/EL2分类体系）

使用示例：
    from core.kg.kg_config import KGConfig
    config = KGConfig.from_yaml()
    if config.enabled:
        driver = config.get_neo4j_driver()

    from core.kg.kg_config import load_domain_config
    domain = load_domain_config()
    el1_nodes = domain.get_el1_nodes()
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
class RetrievalConfig:
    max_context_tokens: int = 8000
    vector_top_k: int = 20
    graph_expand_depth: int = 1
    graph_expand_limit: int = 50


@dataclass
class DegradationConfig:
    neo4j_timeout_ms: int = 3000
    milvus_timeout_ms: int = 3000
    llm_score_prompt: str = ""


@dataclass
class KGConfig:
    enabled: bool = False
    engine: str = "networkx"
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    milvus: MilvusConfig = field(default_factory=MilvusConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    activation: ActivationConfig = field(default_factory=ActivationConfig)
    integration: IntegrationConfig = field(default_factory=IntegrationConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    degradation: DegradationConfig = field(default_factory=DegradationConfig)

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

        retrieval_raw = kg_raw.get("retrieval", {})
        retrieval_cfg = RetrievalConfig(
            max_context_tokens=retrieval_raw.get("max_context_tokens", 8000),
            vector_top_k=retrieval_raw.get("vector_top_k", 20),
            graph_expand_depth=retrieval_raw.get("graph_expand_depth", 1),
            graph_expand_limit=retrieval_raw.get("graph_expand_limit", 50),
        )

        degradation_raw = kg_raw.get("degradation", {})
        degradation_cfg = DegradationConfig(
            neo4j_timeout_ms=degradation_raw.get("neo4j_timeout_ms", 3000),
            milvus_timeout_ms=degradation_raw.get("milvus_timeout_ms", 3000),
            llm_score_prompt=degradation_raw.get("llm_score_prompt", ""),
        )

        config = cls(
            enabled=kg_raw.get("enabled", False),
            engine=kg_raw.get("engine", ""),
            neo4j=neo4j_cfg,
            milvus=milvus_cfg,
            embedding=embedding_cfg,
            activation=activation_cfg,
            integration=integration_cfg,
            retrieval=retrieval_cfg,
            degradation=degradation_cfg,
        )

        if not config.engine or config.engine == "networkx":
            config._auto_detect_engine()

        logger.info(
            f"KG config loaded: enabled={config.enabled}, engine={config.engine}, "
            f"neo4j={config.neo4j.url}, milvus={config.milvus.host}:{config.milvus.port}"
        )
        return config


@dataclass
class DomainConfig:
    domain_name: str = ""
    domain_name_en: str = ""
    el1_nodes: list = field(default_factory=list)
    el2_nodes: list = field(default_factory=list)
    threshold_keywords: list = field(default_factory=list)
    known_thresholds: dict = field(default_factory=dict)

    def get_el1_nodes(self) -> list:
        return self.el1_nodes

    def get_el2_nodes(self) -> list:
        return self.el2_nodes

    def get_all_node_ids(self) -> set:
        ids = set()
        for n in self.el1_nodes:
            ids.add(n.get("id", "").upper())
        for n in self.el2_nodes:
            ids.add(n.get("id", "").upper())
        return ids

    def merge_with_disease_config(
        self, disease_el1: list, disease_el2: list
    ) -> "DomainConfig":
        existing_el1_ids = {n.get("id", "").upper() for n in self.el1_nodes}
        existing_el2_ids = {n.get("id", "").upper() for n in self.el2_nodes}

        merged_el1 = list(self.el1_nodes)
        for n in disease_el1:
            if n.get("id", "").upper() not in existing_el1_ids:
                merged_el1.append(n)
                existing_el1_ids.add(n.get("id", "").upper())

        merged_el2 = list(self.el2_nodes)
        for n in disease_el2:
            if n.get("id", "").upper() not in existing_el2_ids:
                merged_el2.append(n)
                existing_el2_ids.add(n.get("id", "").upper())

        return DomainConfig(
            domain_name=self.domain_name,
            domain_name_en=self.domain_name_en,
            el1_nodes=merged_el1,
            el2_nodes=merged_el2,
        )


_domain_config_cache: Optional[DomainConfig] = None


def load_domain_config(config_path: Optional[str] = None) -> DomainConfig:
    global _domain_config_cache
    if _domain_config_cache is not None:
        return _domain_config_cache

    if config_path is None:
        project_root = Path(__file__).parent.parent.parent
        config_path = str(project_root / "data" / "domain_configs" / "rare_liver_disease.yaml")

    if not Path(config_path).exists():
        logger.warning(f"Domain config not found: {config_path}")
        _domain_config_cache = DomainConfig()
        return _domain_config_cache

    if not YAML_AVAILABLE:
        logger.warning("PyYAML not installed, domain config unavailable")
        _domain_config_cache = DomainConfig()
        return _domain_config_cache

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load domain config: {e}")
        _domain_config_cache = DomainConfig()
        return _domain_config_cache

    domain_raw = data.get("domain", {})
    config = DomainConfig(
        domain_name=domain_raw.get("name", ""),
        domain_name_en=domain_raw.get("name_en", ""),
        el1_nodes=data.get("el1_nodes", []),
        el2_nodes=data.get("el2_nodes", []),
        threshold_keywords=data.get("threshold_keywords", []),
        known_thresholds=data.get("known_thresholds", {}),
    )

    logger.info(
        f"Domain config loaded: {config.domain_name}, "
        f"EL1={len(config.el1_nodes)}, EL2={len(config.el2_nodes)}, "
        f"keywords={len(config.threshold_keywords)}, "
        f"thresholds={len(config.known_thresholds)}"
    )
    _domain_config_cache = config
    return config
