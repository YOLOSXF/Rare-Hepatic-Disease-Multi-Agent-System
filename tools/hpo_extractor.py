"""
HPO 术语提取器（增强版）
使用真正的 HPO 本体库

功能：
1. 从病历文本提取表型术语
2. 加载 HPO 本体文件（obo 格式）
3. 语义相似度匹配
4. 支持中文术语映射
"""

from typing import List, Dict, Any, Optional, Tuple
from loguru import logger
import json
import re
from pathlib import Path
import pandas as pd

# 尝试导入 HPO 库
try:
    import obonet
    from rapidfuzz import process, fuzz
    HPO_LIB_AVAILABLE = True
except ImportError:
    HPO_LIB_AVAILABLE = False
    logger.warning("HPO 库未安装，使用简化模式。安装：pip install obonet rapidfuzz")


class HPOExtractor:
    """
    HPO 术语提取器（增强版）
    
    使用 LLM 从病历文本提取表型术语，并映射到 HPO 代码
    """
    
    # 中文到英文的医学术语映射（用于 HPO 匹配）
    CHINESE_TO_ENGLISH_TERMS = {
        "黄疸": "Jaundice",
        "乏力": "Fatigue",
        "腹胀": "Abdominal distension",
        "食欲不振": "Decreased appetite",
        "恶心": "Nausea",
        "呕吐": "Vomiting",
        "腹痛": "Abdominal pain",
        "肝区疼痛": "Hepatic pain",
        "肝肿大": "Hepatomegaly",
        "脾肿大": "Splenomegaly",
        "腹水": "Ascites",
        "蜘蛛痣": "Spider angioma",
        "肝掌": "Palmar erythema",
        "震颤": "Tremor",
        "构音障碍": "Dysarthria",
        "肌张力障碍": "Dystonia",
        "行为异常": "Behavioral abnormality",
        "精神症状": "Psychiatric symptoms",
        "转氨酶升高": "Elevated transaminases",
        "胆红素升高": "Hyperbilirubinemia",
        "凝血功能异常": "Coagulation abnormality",
        "肝硬化": "Liver cirrhosis",
        "脂肪肝": "Hepatic steatosis",
        "肝纤维化": "Hepatic fibrosis",
        "门静脉高压": "Portal hypertension",
        "食管静脉曲张": "Esophageal varices",
        "意识障碍": "Encephalopathy",
        "昏迷": "Coma",
        "抽搐": "Seizures",
        "贫血": "Anemia",
        "血小板减少": "Thrombocytopenia",
        "白细胞减少": "Leukopenia",
        "发热": "Fever",
        "体重下降": "Weight loss",
        "消瘦": "Cachexia",
    }
    
    def __init__(
        self,
        llm_client=None,
        config_path: str = "config.yaml",
        hpo_obo_path: Optional[str] = None
    ):
        """
        初始化 HPO 提取器
        
        Args:
            llm_client: LLM 客户端（可选）
            config_path: 配置文件路径
            hpo_obo_path: HPO 本体文件路径（obo 格式）
        """
        self.config_path = config_path
        self.llm_client = llm_client
        self._llm_initialized = False
        
        # HPO 本体数据
        self.hpo_graph = None
        self.hpo_terms = {}
        self.hpo_synonyms = {}
        
        # 加载 HPO 本体
        if hpo_obo_path and HPO_LIB_AVAILABLE:
            self.load_hpo_ontology(hpo_obo_path)
        elif HPO_LIB_AVAILABLE:
            # 尝试从默认路径加载
            default_paths = [
                "hpo/hp.obo",
                "../hpo/hp.obo",
                "/data/hpo/hp.obo"
            ]
            for path in default_paths:
                if Path(path).exists():
                    self.load_hpo_ontology(path)
                    break
    
    def load_hpo_ontology(self, obo_path: str):
        """
        加载 HPO 本体文件（obo 格式）
        
        Args:
            obo_path: HPO obo 文件路径
        """
        if not HPO_LIB_AVAILABLE:
            logger.warning("HPO 库未安装，无法加载本体文件")
            return
        
        try:
            logger.info(f"Loading HPO ontology from {obo_path}...")
            
            # 使用 obonet 加载 obo 文件
            self.hpo_graph = obonet.read_obo(obo_path)
            
            # 构建术语索引
            for node_id, data in self.hpo_graph.nodes(data=True):
                if node_id.startswith('HP:'):
                    # 主术语
                    name = data.get('name', '')
                    if name:
                        self.hpo_terms[name.lower()] = {
                            'hpo_id': node_id,
                            'name': name,
                            'definition': data.get('def', ''),
                            'synonyms': []
                        }
                    
                    # 同义词
                    synonyms = data.get('synonym', [])
                    for synonym in synonyms:
                        # 解析同义词（格式："term" EXACT []）
                        match = re.search(r'"([^"]+)"', synonym)
                        if match:
                            synonym_term = match.group(1).lower()
                            self.hpo_synonyms[synonym_term] = node_id
            
            logger.info(f"Loaded {len(self.hpo_terms)} HPO terms with {len(self.hpo_synonyms)} synonyms")
            
        except Exception as e:
            logger.error(f"Failed to load HPO ontology: {e}")
    
    def _get_llm_client(self):
        """懒加载 LLM 客户端"""
        if not self._llm_initialized:
            from core.llm_client import LLMClient
            self.llm_client = LLMClient.from_env()
            self._llm_initialized = True
            logger.info(f"HPOExtractor LLM initialized: {self.llm_client.model}")
        return self.llm_client
    
    def extract_phenotypes(self, text: str) -> List[str]:
        """
        从文本中提取表型术语
        
        Args:
            text: 病历文本
        
        Returns:
            表型术语列表
        """
        try:
            llm = self._get_llm_client()
            
            system_prompt = """你是一名医学专家，擅长从病历中提取表型术语。
请从提供的病历文本中提取所有表型术语（症状、体征、实验室异常等）。

要求：
1. 只提取医学术语，不要提取诊断名称
2. 使用标准医学术语
3. 输出 JSON 格式：{"phenotypes": ["术语 1", "术语 2", ...]}

示例输入：
"患者乏力、黄疸 2 周，查体肝肋下 3cm，转氨酶升高"

示例输出：
{"phenotypes": ["乏力", "黄疸", "肝肿大", "转氨酶升高"]}
"""
            
            response = llm.complete(
                prompt=f"请从以下病历中提取表型术语：\n\n{text}",
                system_prompt=system_prompt,
                max_tokens=500
            )
            
            # 解析 JSON
            try:
                response = response.strip()
                if response.startswith("```json"):
                    response = response[7:]
                if response.endswith("```"):
                    response = response[:-3]
                response = response.strip()
                
                result = json.loads(response)
                phenotypes = result.get("phenotypes", [])
                logger.info(f"Extracted {len(phenotypes)} phenotypes using LLM")
                return phenotypes
                
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response as JSON: {e}")
                return self._extract_by_rules(text)
                
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return self._extract_by_rules(text)
    
    def _extract_by_rules(self, text: str) -> List[str]:
        """
        使用规则提取表型术语（降级方案）
        
        Args:
            text: 病历文本
        
        Returns:
            表型术语列表
        """
        phenotypes = []
        
        # 遍历中文术语字典，匹配文本
        for term in self.CHINESE_TO_ENGLISH_TERMS.keys():
            if term in text:
                phenotypes.append(term)
        
        logger.info(f"Extracted {len(phenotypes)} phenotypes using rules")
        return phenotypes
    
    def map_to_hpo(self, phenotypes: List[str]) -> List[Dict[str, Any]]:
        """
        将表型术语映射到 HPO 代码
        
        Args:
            phenotypes: 表型术语列表
        
        Returns:
            HPO 映射结果列表
        """
        results = []
        
        for phenotype in phenotypes:
            result = self._map_single_phenotype(phenotype)
            results.append(result)
        
        # 统计
        mapped_count = sum(1 for r in results if r["hpo_id"] is not None)
        logger.info(f"Mapped {mapped_count}/{len(results)} phenotypes to HPO")
        
        return results
    
    def _map_single_phenotype(self, phenotype: str) -> Dict[str, Any]:
        """
        映射单个表型术语到 HPO
        
        Args:
            phenotype: 表型术语
        
        Returns:
            HPO 映射结果
        """
        # 方法 1：中文术语直接映射
        if phenotype in self.CHINESE_TO_ENGLISH_TERMS:
            english_term = self.CHINESE_TO_ENGLISH_TERMS[phenotype]
            
            # 如果有 HPO 本体，查找精确匹配
            if self.hpo_graph:
                hpo_id = self._find_hpo_by_name(english_term)
                if hpo_id:
                    return {
                        "phenotype": phenotype,
                        "hpo_id": hpo_id,
                        "hpo_name": english_term,
                        "match_type": "exact_chinese_to_english"
                    }
            
            # 降级：使用预定义的 HPO ID（简化版）
            return {
                "phenotype": phenotype,
                "hpo_id": self._get_fallback_hpo_id(phenotype),
                "hpo_name": english_term,
                "match_type": "fallback"
            }
        
        # 方法 2：使用 HPO 本体模糊匹配
        if self.hpo_graph and HPO_LIB_AVAILABLE:
            hpo_id = self._fuzzy_match_hpo(phenotype)
            if hpo_id:
                term_data = self.hpo_graph.nodes[hpo_id]
                return {
                    "phenotype": phenotype,
                    "hpo_id": hpo_id,
                    "hpo_name": term_data.get('name', ''),
                    "match_type": "fuzzy"
                }
        
        # 未匹配
        return {
            "phenotype": phenotype,
            "hpo_id": None,
            "hpo_name": None,
            "match_type": "unmapped"
        }
    
    def _find_hpo_by_name(self, name: str) -> Optional[str]:
        """
        根据英文名称查找 HPO ID
        
        Args:
            name: 英文术语名
        
        Returns:
            HPO ID 或 None
        """
        name_lower = name.lower()
        
        # 精确匹配
        if name_lower in self.hpo_terms:
            return self.hpo_terms[name_lower]['hpo_id']
        
        # 同义词匹配
        if name_lower in self.hpo_synonyms:
            return self.hpo_synonyms[name_lower]
        
        return None
    
    def _fuzzy_match_hpo(self, text: str) -> Optional[str]:
        """
        模糊匹配 HPO 术语
        
        Args:
            text: 文本
        
        Returns:
            最佳匹配的 HPO ID
        """
        if not HPO_LIB_AVAILABLE:
            return None
        
        try:
            # 使用 RapidFuzz 进行模糊匹配
            choices = list(self.hpo_terms.keys())
            
            # 提取匹配
            match = process.extractOne(text.lower(), choices, scorer=fuzz.ratio)
            
            if match and match[1] >= 80:  # 相似度阈值 80%
                return self.hpo_terms[match[0]]['hpo_id']
            
            # 同义词匹配
            match = process.extractOne(text.lower(), list(self.hpo_synonyms.keys()), scorer=fuzz.ratio)
            if match and match[1] >= 80:
                return self.hpo_synonyms[match[0]]
            
        except Exception as e:
            logger.debug(f"Fuzzy matching failed: {e}")
        
        return None
    
    def _get_fallback_hpo_id(self, phenotype: str) -> Optional[str]:
        """
        获取预定义的 HPO ID（降级方案）
        
        Args:
            phenotype: 表型术语
        
        Returns:
            HPO ID 或 None
        """
        fallback_map = {
            "黄疸": "HP:0000952",
            "乏力": "HP:0012378",
            "腹胀": "HP:0003373",
            "食欲不振": "HP:0002039",
            "恶心": "HP:0002018",
            "呕吐": "HP:0002013",
            "腹痛": "HP:0002027",
            "肝区疼痛": "HP:0030016",
            "肝肿大": "HP:0002246",
            "脾肿大": "HP:0001744",
            "腹水": "HP:0001541",
            "蜘蛛痣": "HP:0012040",
            "肝掌": "HP:0030017",
            "震颤": "HP:0001337",
            "构音障碍": "HP:0001260",
            "肌张力障碍": "HP:0003457",
            "行为异常": "HP:0000708",
            "精神症状": "HP:0000708",
            "转氨酶升高": "HP:0002910",
            "胆红素升高": "HP:0002908",
            "凝血功能异常": "HP:0003255",
        }
        
        return fallback_map.get(phenotype)
    
    def extract_and_map(self, text: str) -> List[Dict[str, Any]]:
        """
        提取表型并映射到 HPO（一站式方法）
        
        Args:
            text: 病历文本
        
        Returns:
            HPO 映射结果列表
        """
        phenotypes = self.extract_phenotypes(text)
        return self.map_to_hpo(phenotypes)
    
    def get_hpo_info(self, hpo_id: str) -> Optional[Dict[str, Any]]:
        """
        获取 HPO 术语详细信息
        
        Args:
            hpo_id: HPO ID（如 HP:0000952）
        
        Returns:
            HPO 术语信息
        """
        if not self.hpo_graph:
            return None
        
        if hpo_id in self.hpo_graph.nodes:
            data = self.hpo_graph.nodes[hpo_id]
            return {
                'hpo_id': hpo_id,
                'name': data.get('name', ''),
                'definition': data.get('def', ''),
                'synonyms': data.get('synonym', []),
                'parents': list(self.hpo_graph.predecessors(hpo_id))
            }
        
        return None


# ==================== 使用示例 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("HPO 术语提取器测试（增强版）")
    print("=" * 60)
    print()
    
    # 检查 HPO 库
    if HPO_LIB_AVAILABLE:
        print("✅ HPO 库已安装")
    else:
        print("⚠️  HPO 库未安装，使用简化模式")
        print("   安装：pip install obonet rapidfuzz")
    print()
    
    # 创建提取器
    extractor = HPOExtractor()
    
    # 测试文本
    test_text = """
    患者男性，23 岁，因"乏力、黄疸 2 周，伴手部震颤"入院。
    查体：神清，肝肋下 3cm，质中，脾肋下 2cm。
    实验室检查：ALT 125 U/L，AST 98 U/L，TBil 52.5 μmol/L，
    铜蓝蛋白 0.08 g/L（降低）。
    """
    
    print(f"测试文本:\n{test_text}")
    print()
    
    # 提取并映射
    print("提取 HPO 术语...")
    results = extractor.extract_and_map(test_text)
    
    print(f"\n提取结果 ({len(results)} 个表型):")
    print("-" * 60)
    for result in results:
        if result["hpo_id"]:
            print(f"✅ {result['phenotype']:10s} → {result['hpo_id']:15s} ({result['hpo_name']})")
            print(f"   匹配类型：{result['match_type']}")
        else:
            print(f"⚠️  {result['phenotype']:10s} → 未映射")
    
    print()
    print("=" * 60)
    
    # 测试 HPO 本体加载
    if extractor.hpo_graph:
        print(f"\nHPO 本体已加载：{len(extractor.hpo_graph.nodes)} 个节点")
        
        # 测试查询
        info = extractor.get_hpo_info("HP:0000952")
        if info:
            print(f"\n示例查询 (HP:0000952):")
            print(f"  名称：{info['name']}")
            print(f"  定义：{info['definition'][:100]}...")