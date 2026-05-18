"""
通用疾病知识图谱构建插件包

新增疾病两种方式：
1. 手动创建YAML配置文件 → DiseasePipeline加载
2. PDF优先模式 → DiseasePipeline.from_pdfs() 直接从PDF提取

使用示例：
    # 方式1：手动YAML
    from core.kg.diseases import DiseasePipeline
    wilson = DiseasePipeline("data/disease_configs/wilson_disease.yaml")
    result = await wilson.build()

    # 方式2：PDF优先模式（无需YAML）
    from core.kg.diseases import DiseasePipeline
    pipeline = DiseasePipeline.from_pdfs(
        disease_id="PBC",
        disease_name="原发性胆汁性胆管炎",
        pdf_paths=["data/guidelines/PBC/pbc.pdf"],
    )
    result = await pipeline.build()
"""

from core.kg.diseases.disease_pipeline import DiseasePipeline

__all__ = ["DiseasePipeline"]
