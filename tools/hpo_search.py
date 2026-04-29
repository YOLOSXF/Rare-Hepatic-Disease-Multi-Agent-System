"""
HPO（人类表型本体）搜索工具
参考 DeepRare 的 hpo_search.py 实现
"""

from typing import List, Dict, Optional
import requests
from loguru import logger


class HPOSearchTool:
    """
    HPO 表型搜索工具
    
    使用 HPO API 搜索表型术语和相关疾病
    """
    
    def __init__(self, api_base: str = "https://hpo.jax.org/api"):
        """
        初始化工具
        
        Args:
            api_base: HPO API 基础 URL
        """
        self.api_base = api_base
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "Medical-Agent/1.0"
        })
    
    def search_phenotype(self, term: str) -> List[Dict]:
        """
        搜索表型术语
        
        Args:
            term: 表型术语
        
        Returns:
            匹配的 HPO 术语列表
        """
        try:
            url = f"{self.api_base}/search"
            params = {
                "query": term,
                "category": "phenotype",
                "limit": 10
            }
            
            response = self.session.get(url, params=params)
            data = response.json()
            
            results = []
            for item in data.get("results", []):
                results.append({
                    "hpo_id": item.get("id", ""),
                    "label": item.get("label", ""),
                    "definition": item.get("definition", ""),
                    "synonyms": item.get("synonyms", [])
                })
            
            return results
            
        except Exception as e:
            logger.error(f"HPO phenotype search failed: {e}")
            return []
    
    def get_diseases_for_phenotype(self, hpo_id: str, top_k: int = 5) -> List[Dict]:
        """
        获取与表型相关的疾病
        
        Args:
            hpo_id: HPO 术语 ID
            top_k: 返回疾病数量
        
        Returns:
            相关疾病列表
        """
        try:
            url = f"{self.api_base}/phenotype/{hpo_id}/diseases"
            params = {"limit": top_k}
            
            response = self.session.get(url, params=params)
            data = response.json()
            
            diseases = []
            for item in data.get("diseases", []):
                diseases.append({
                    "disease_id": item.get("diseaseId", ""),
                    "disease_name": item.get("diseaseName", ""),
                    "frequency": item.get("frequency", ""),
                    "reference": item.get("reference", "")
                })
            
            return diseases
            
        except Exception as e:
            logger.error(f"HPO disease lookup failed: {e}")
            return []
    
    def annotate_phenotypes(self, phenotype_terms: List[str]) -> Dict:
        """
        注释表型术语列表
        
        Args:
            phenotype_terms: 表型术语列表
        
        Returns:
            注释结果
        """
        annotated_terms = []
        disease_associations = []
        
        for term in phenotype_terms:
            # 搜索 HPO 术语
            hpo_results = self.search_phenotype(term)
            
            if hpo_results:
                best_match = hpo_results[0]
                annotated_terms.append({
                    "input_term": term,
                    "hpo_id": best_match["hpo_id"],
                    "hpo_label": best_match["label"],
                    "confidence": "high" if term.lower() in best_match["label"].lower() else "medium"
                })
                
                # 获取相关疾病
                diseases = self.get_diseases_for_phenotype(best_match["hpo_id"])
                disease_associations.extend(diseases)
        
        return {
            "annotated_terms": annotated_terms,
            "disease_associations": disease_associations,
            "total_terms": len(phenotype_terms),
            "annotated_count": len(annotated_terms)
        }
    
    def get_phenotype_tree(self, hpo_id: str) -> Dict:
        """
        获取表型术语树结构
        
        Args:
            hpo_id: HPO 术语 ID
        
        Returns:
            术语树结构
        """
        try:
            url = f"{self.api_base}/phenotype/{hpo_id}/tree"
            response = self.session.get(url)
            return response.json()
        except Exception as e:
            logger.error(f"HPO tree fetch failed: {e}")
            return {}
