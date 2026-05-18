"""
知识图谱模块

提供罕见肝病知识图谱的构建、检索和集成功能：
- kg_schema: 数据类定义（DiseaseNode, FeatureNode, RelationEdge, ContradictEdge等）
- kg_config: KG系统配置加载
- kg_cache: LLM调用缓存
- kg_chunker: PDF指南分块（优化粒度：360字/Chunk）
- kg_extractor: LLM一步提取（实体+关系+差异诊断+矛盾排除）
- kg_validator: 抽取结果校验
- kg_importer: 四层KG导入（含差异/矛盾边）
- kg_writer: 图存储写入（NetworkX/Neo4j，含CONTRADICTS边）
- kg_cleaner: 图谱去重与一致性校验
- kg_embedder: 实体嵌入与Milvus索引
- kg_differential: 差异诊断KG（支持ContradictEdge对象）
- kg_builder: 构建入口（含人工审核预留接口）
- kg_review: 人工审核接口（导出/导入/修正）
- kg_retriever: 检索引擎
- kg_classifier: 激活分类器
- kg_interface: 统一接口
"""
