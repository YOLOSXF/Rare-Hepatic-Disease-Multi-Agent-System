"""
向量嵌入与Milvus索引构建模块

职责：
1. 从Neo4j读取EL4/EL3节点生成BGE-M3嵌入
2. 从指南PDF目录读取分块生成嵌入
3. 写入Milvus向量索引
4. 嵌入质量验证(可配置同义/反义测试对)
5. 向量相似性检索

所有疾病特定路径和测试对通过构造参数传入，本模块不硬编码任何疾病知识。

使用示例：
    from core.kg.kg_embedder import KGEmbedder

    embedder = KGEmbedder(
        guidelines_dir="data/guidelines/肝豆状核变性 Hepatolenticular Degeneration",
        quality_synonym_pairs=[("铜蓝蛋白降低", "ceruloplasmin decreased")],
    )
    embedder.embed_all()
    results = embedder.search("铜蓝蛋白降低", top_k=5)
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

from core.kg.kg_config import KGConfig


class KGEmbedder:
    def __init__(
        self,
        config: Optional[KGConfig] = None,
        guidelines_dir: Optional[str] = None,
        quality_synonym_pairs: Optional[List[Tuple[str, str]]] = None,
        quality_dissimilar_pairs: Optional[List[Tuple[str, str]]] = None,
    ):
        self.config = config or KGConfig.from_yaml()
        self._model = None
        self._milvus_client = None
        self.collection_name = self.config.milvus.collection_name
        self.embedding_dim = self.config.embedding.dim
        self._embeddings_cache_dir = Path("data/kg_embeddings")
        self._embeddings_cache_dir.mkdir(parents=True, exist_ok=True)

        project_root = Path(__file__).parent.parent.parent
        if guidelines_dir:
            self.guidelines_dir = Path(guidelines_dir)
            if not self.guidelines_dir.is_absolute():
                self.guidelines_dir = project_root / guidelines_dir
        else:
            self.guidelines_dir = None

        self.quality_synonym_pairs = quality_synonym_pairs or []
        self.quality_dissimilar_pairs = quality_dissimilar_pairs or []

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            model_path = self.config.embedding.get_model_path()
            if os.path.isdir(model_path):
                logger.info(f"Loading BGE-M3 from local path: {model_path}")
            else:
                logger.info(f"Loading BGE-M3 from HuggingFace: {model_path}")
            self._model = SentenceTransformer(model_path)
            logger.info(f"BGE-M3 model loaded, dim={self._model.get_sentence_embedding_dimension()}")
        return self._model

    def _get_milvus_client(self):
        if self._milvus_client is None:
            from pymilvus import MilvusClient
            self._milvus_client = MilvusClient(
                uri=f"http://{self.config.milvus.host}:{self.config.milvus.port}"
            )
            logger.info(f"Milvus client connected: {self.config.milvus.host}:{self.config.milvus.port}")
        return self._milvus_client

    def create_collection(self) -> None:
        client = self._get_milvus_client()
        if client.has_collection(self.collection_name):
            logger.info(f"Milvus collection '{self.collection_name}' already exists")
            return

        from pymilvus import CollectionSchema, FieldSchema, DataType

        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="entity_name", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="entity_type", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="layer", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="description", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="source_guideline", dtype=DataType.VARCHAR, max_length=256),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
        ]
        schema = CollectionSchema(fields=fields, auto_id=True, enable_dynamic_field=False)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128},
        )

        client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info(f"Milvus collection '{self.collection_name}' created (dim={self.embedding_dim})")

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        model = self._get_model()
        embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=True)
        return embeddings

    def embed_entity(self, name: str, description: str = "") -> np.ndarray:
        text = f"{name}: {description}" if description else name
        return self.embed_texts([text])[0]

    def _get_npy_path(self, prefix: str) -> Path:
        return self._embeddings_cache_dir / f"{prefix}_embeddings.npy"

    def _save_embeddings(self, prefix: str, embeddings: np.ndarray, metadata: List[Dict]) -> None:
        npy_path = self._get_npy_path(prefix)
        np.save(npy_path, embeddings)
        meta_path = self._embeddings_cache_dir / f"{prefix}_metadata.json"
        import json
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        logger.info(f"Embeddings saved: {npy_path} ({embeddings.shape})")

    def _load_embeddings(self, prefix: str) -> Optional[Tuple[np.ndarray, List[Dict]]]:
        npy_path = self._get_npy_path(prefix)
        meta_path = self._embeddings_cache_dir / f"{prefix}_metadata.json"
        if npy_path.exists() and meta_path.exists():
            embeddings = np.load(npy_path)
            import json
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            logger.info(f"Embeddings loaded from cache: {npy_path} ({embeddings.shape})")
            return embeddings, metadata
        return None

    def embed_el4_features(self) -> Tuple[np.ndarray, List[Dict]]:
        cached = self._load_embeddings("el4_features")
        if cached is not None:
            return cached

        driver = self.config.get_neo4j_driver()
        with driver.session(database=self.config.neo4j.database) as session:
            result = session.run("""
                MATCH (f:Feature)
                RETURN f.id AS id, f.name AS name, f.layer AS layer,
                       f.category AS category, f.description AS description,
                       f.is_core AS is_core
                ORDER BY f.layer, f.name
            """)
            features = [dict(r) for r in result]
        driver.close()

        if not features:
            logger.warning("No EL4 features found in Neo4j")
            return np.array([]), []

        texts = []
        for f in features:
            desc = f.get("description", "") or ""
            name = f.get("name", "")
            text = f"{name}: {desc}" if desc else name
            texts.append(text)

        logger.info(f"Generating embeddings for {len(features)} EL4 features...")
        embeddings = self.embed_texts(texts)

        metadata = [
            {
                "entity_name": f.get("name", ""),
                "entity_type": "Feature",
                "layer": f.get("layer", "EL4d"),
                "description": f.get("description", "")[:2048],
                "source_guideline": "",
            }
            for f in features
        ]

        self._save_embeddings("el4_features", embeddings, metadata)
        return embeddings, metadata

    def embed_el3_diseases(self) -> Tuple[np.ndarray, List[Dict]]:
        cached = self._load_embeddings("el3_diseases")
        if cached is not None:
            return cached

        driver = self.config.get_neo4j_driver()
        with driver.session(database=self.config.neo4j.database) as session:
            result = session.run("""
                MATCH (d:Disease)
                OPTIONAL MATCH (d)-[r:HAS_MANIFESTATION|HAS_DIAGNOSTIC_KEY]->(f:Feature)
                WHERE f.is_core = true
                WITH d, collect(f.name) AS core_features
                RETURN d.id AS id, d.name AS name, d.layer AS layer,
                       d.description AS description,
                       d.icd10 AS icd10, d.omim AS omim,
                       core_features
                ORDER BY d.name
            """)
            diseases = [dict(r) for r in result]
        driver.close()

        if not diseases:
            logger.warning("No EL3 diseases found in Neo4j")
            return np.array([]), []

        texts = []
        for d in diseases:
            name = d.get("name", "")
            desc = d.get("description", "") or ""
            core = d.get("core_features", [])
            core_str = "、".join(core) if core else ""
            text = f"{name}: {desc}"
            if core_str:
                text += f" 核心特征包括：{core_str}"
            texts.append(text)

        logger.info(f"Generating embeddings for {len(diseases)} EL3 diseases...")
        embeddings = self.embed_texts(texts)

        metadata = [
            {
                "entity_name": d.get("name", ""),
                "entity_type": "Disease",
                "layer": d.get("layer", "EL3"),
                "description": d.get("description", "")[:2048],
                "source_guideline": "",
            }
            for d in diseases
        ]

        self._save_embeddings("el3_diseases", embeddings, metadata)
        return embeddings, metadata

    def embed_guideline_chunks(self) -> Tuple[np.ndarray, List[Dict]]:
        cached = self._load_embeddings("guideline_chunks")
        if cached is not None:
            return cached

        if self.guidelines_dir is None or not self.guidelines_dir.exists():
            logger.warning(f"Guidelines directory not configured or does not exist: {self.guidelines_dir}")
            return np.array([]), []

        from core.kg.kg_chunker import MedicalChunker
        chunker = MedicalChunker()

        all_chunks = []
        for pdf_path in self.guidelines_dir.glob("*.pdf"):
            source_name = pdf_path.stem
            chunks = chunker.chunk_pdf(str(pdf_path), source_name=source_name)
            all_chunks.extend(chunks)
            logger.info(f"Chunked {pdf_path.name}: {len(chunks)} chunks")

        if not all_chunks:
            logger.warning("No guideline chunks found")
            return np.array([]), []

        texts = [c.content for c in all_chunks]

        logger.info(f"Generating embeddings for {len(all_chunks)} guideline chunks...")
        embeddings = self.embed_texts(texts, batch_size=16)

        metadata = [
            {
                "entity_name": f"chunk_{c.chunk_id}",
                "entity_type": "GuidelineChunk",
                "layer": "Guideline",
                "description": c.content[:2048],
                "source_guideline": c.source or "",
            }
            for c in all_chunks
        ]

        self._save_embeddings("guideline_chunks", embeddings, metadata)
        return embeddings, metadata

    @staticmethod
    def _truncate_to_bytes(text: str, max_bytes: int) -> str:
        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text
        truncated = encoded[:max_bytes]
        try:
            return truncated.decode("utf-8")
        except UnicodeDecodeError:
            return truncated[:truncated.rfind(b"\n", 0, max_bytes)].decode("utf-8", errors="ignore")

    def write_to_milvus(self, metadata: List[Dict], embeddings: np.ndarray) -> int:
        self.create_collection()
        client = self._get_milvus_client()

        data = []
        for i, meta in enumerate(metadata):
            data.append({
                "entity_name": self._truncate_to_bytes(meta.get("entity_name", ""), 256),
                "entity_type": self._truncate_to_bytes(meta.get("entity_type", ""), 64),
                "layer": self._truncate_to_bytes(meta.get("layer", ""), 32),
                "description": self._truncate_to_bytes(meta.get("description", ""), 2000),
                "source_guideline": self._truncate_to_bytes(meta.get("source_guideline", ""), 256),
                "embedding": embeddings[i].tolist(),
            })

        batch_size = 100
        total = 0
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            try:
                client.insert(collection_name=self.collection_name, data=batch)
                total += len(batch)
            except Exception as e:
                logger.error(f"Milvus insert batch {i//batch_size} failed: {e}")
                for j, item in enumerate(batch):
                    try:
                        client.insert(collection_name=self.collection_name, data=[item])
                        total += 1
                    except Exception as e2:
                        logger.warning(f"Skip item {i+j}: {e2}")

        logger.info(f"Wrote {total} vectors to Milvus collection '{self.collection_name}'")
        return total

    def embed_all(self) -> Dict[str, int]:
        self.create_collection()

        stats = {}

        el4_embeddings, el4_metadata = self.embed_el4_features()
        if len(el4_embeddings) > 0:
            stats["el4_features"] = self.write_to_milvus(el4_metadata, el4_embeddings)
        else:
            stats["el4_features"] = 0

        el3_embeddings, el3_metadata = self.embed_el3_diseases()
        if len(el3_embeddings) > 0:
            stats["el3_diseases"] = self.write_to_milvus(el3_metadata, el3_embeddings)
        else:
            stats["el3_diseases"] = 0

        gc_embeddings, gc_metadata = self.embed_guideline_chunks()
        if len(gc_embeddings) > 0:
            stats["guideline_chunks"] = self.write_to_milvus(gc_metadata, gc_embeddings)
        else:
            stats["guideline_chunks"] = 0

        logger.info(f"Embed all complete: {stats}")
        return stats

    def search(
        self,
        query: str,
        top_k: int = 5,
        layer: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> List[Dict]:
        client = self._get_milvus_client()

        query_embedding = self.embed_texts([query])[0]

        filter_expr = ""
        conditions = []
        if layer:
            conditions.append(f'layer == "{layer}"')
        if entity_type:
            conditions.append(f'entity_type == "{entity_type}"')
        if conditions:
            filter_expr = " and ".join(conditions)

        search_params = {
            "metric_type": "COSINE",
            "params": {"radius": 0.2, "range_filter": 1.0},
        }

        results = client.search(
            collection_name=self.collection_name,
            data=[query_embedding.tolist()],
            limit=top_k,
            output_fields=["entity_name", "entity_type", "layer", "description", "source_guideline"],
            search_params=search_params,
            filter=filter_expr if filter_expr else None,
        )

        parsed = []
        if results and results[0]:
            for r in results[0]:
                entity = r.get("entity", {})
                parsed.append({
                    "entity_name": entity.get("entity_name", ""),
                    "entity_type": entity.get("entity_type", ""),
                    "layer": entity.get("layer", ""),
                    "description": entity.get("description", ""),
                    "source_guideline": entity.get("source_guideline", ""),
                    "distance": r.get("distance", 0.0),
                })

        return parsed

    def validate_quality(
        self,
        synonym_pairs: Optional[List[Tuple[str, str]]] = None,
        dissimilar_pairs: Optional[List[Tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "synonym_pairs": [],
            "dissimilar_pairs": [],
            "passed": True,
        }

        syn_tests = synonym_pairs or self.quality_synonym_pairs
        dis_tests = dissimilar_pairs or self.quality_dissimilar_pairs

        if not syn_tests and not dis_tests:
            logger.info("No quality test pairs configured, skipping validation")
            report["passed"] = True
            report["note"] = "No test pairs configured"
            return report

        for name1, name2 in syn_tests:
            emb1 = self.embed_texts([name1])[0]
            emb2 = self.embed_texts([name2])[0]
            similarity = float(np.dot(emb1, emb2))
            report["synonym_pairs"].append({
                "name1": name1, "name2": name2,
                "similarity": round(similarity, 4),
                "passed": similarity > 0.8,
            })
            if similarity <= 0.8:
                report["passed"] = False

        for name1, name2 in dis_tests:
            emb1 = self.embed_texts([name1])[0]
            emb2 = self.embed_texts([name2])[0]
            similarity = float(np.dot(emb1, emb2))
            report["dissimilar_pairs"].append({
                "name1": name1, "name2": name2,
                "similarity": round(similarity, 4),
                "passed": similarity < 0.5,
            })
            if similarity >= 0.5:
                report["passed"] = False

        logger.info(f"Embedding quality validation: {'PASSED' if report['passed'] else 'FAILED'}")
        return report

    def close(self) -> None:
        if self._milvus_client is not None:
            self._milvus_client.close()
            self._milvus_client = None
            logger.info("Milvus client closed")
