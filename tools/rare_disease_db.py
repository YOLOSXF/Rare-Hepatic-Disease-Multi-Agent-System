"""
罕见病数据库工具
参考 DeepRare 的 Orphanet/OMIM 搜索实现
"""

from typing import List, Dict, Optional
import requests
from loguru import logger


class RareDiseaseDBTool:
    """
    罕见病数据库工具
    
    整合多个罕见病数据源：
    - Orphanet
    - OMIM
    - 中国罕见病诊疗服务信息系统
    """
    
    def __init__(self):
        """初始化工具"""
        self.orphanet_api = "https://www.orpha.net/orsor/"
        self.omim_api = "https://api.omim.org/api"
        
        # 内置罕见病数据库（简化版）
        self.rare_disease_db = self._load_rare_disease_db()
    
    def _load_rare_disease_db(self) -> Dict:
        """加载罕见病数据库"""
        return {
            "Wilson_Disease": {
                "orpha_id": "ORPHA905",
                "omim_id": "277900",
                "name_cn": "肝豆状核变性",
                "name_en": "Wilson Disease",
                "inheritance": "常染色体隐性遗传",
                "gene": "ATP7B",
                "prevalence": "1/30,000",
                "age_of_onset": "5-40 岁",
                "key_symptoms": [
                    "肝功能异常",
                    "神经精神症状",
                    "K-F 环",
                    "铜蓝蛋白降低"
                ],
                "diagnostic_tests": [
                    "血清铜蓝蛋白",
                    "24 小时尿铜",
                    "裂隙灯检查",
                    "ATP7B 基因检测"
                ],
                "treatment": [
                    "青霉胺",
                    "曲恩汀",
                    "锌剂",
                    "低铜饮食"
                ]
            },
            "Autoimmune_Hepatitis": {
                "orpha_id": "ORPHA2137",
                "omim_id": "109250",
                "name_cn": "自身免疫性肝炎",
                "name_en": "Autoimmune Hepatitis",
                "inheritance": "多基因遗传",
                "gene": "HLA-DR3, HLA-DR4",
                "prevalence": "1/100,000",
                "age_of_onset": "任何年龄",
                "key_symptoms": [
                    "乏力",
                    "黄疸",
                    "关节痛",
                    "肝脾肿大"
                ],
                "diagnostic_tests": [
                    "ANA",
                    "SMA",
                    "LKM-1",
                    "IgG",
                    "肝活检"
                ],
                "treatment": [
                    "泼尼松",
                    "硫唑嘌呤",
                    "熊去氧胆酸"
                ]
            },
            "Hereditary_Hemochromatosis": {
                "orpha_id": "ORPHA545",
                "omim_id": "235200",
                "name_cn": "遗传性血色病",
                "name_en": "Hereditary Hemochromatosis",
                "inheritance": "常染色体隐性遗传",
                "gene": "HFE",
                "prevalence": "1/200-1/300 (北欧人群)",
                "age_of_onset": "30-60 岁",
                "key_symptoms": [
                    "皮肤色素沉着",
                    "糖尿病",
                    "肝硬化",
                    "关节痛"
                ],
                "diagnostic_tests": [
                    "转铁蛋白饱和度",
                    "铁蛋白",
                    "HFE 基因检测",
                    "肝脏 MRI T2*"
                ],
                "treatment": [
                    "静脉放血",
                    "去铁胺",
                    "饮食调整"
                ]
            },
            "Primary_Biliary_Cholangitis": {
                "orpha_id": "ORPHA186",
                "omim_id": "118950",
                "name_cn": "原发性胆汁性胆管炎",
                "name_en": "Primary Biliary Cholangitis",
                "inheritance": "多基因遗传",
                "gene": "多个易感基因",
                "prevalence": "1/1000-1/4000",
                "age_of_onset": "30-65 岁",
                "key_symptoms": [
                    "皮肤瘙痒",
                    "乏力",
                    "黄疸",
                    "肝脾肿大"
                ],
                "diagnostic_tests": [
                    "AMA",
                    "AMA-M2",
                    "ALP",
                    "IgM",
                    "肝活检"
                ],
                "treatment": [
                    "熊去氧胆酸",
                    "奥贝胆酸",
                    "非诺贝特"
                ]
            },
            "Alpha1_Antitrypsin_Deficiency": {
                "orpha_id": "ORPHA60",
                "omim_id": "613490",
                "name_cn": "α1-抗胰蛋白酶缺乏症",
                "name_en": "Alpha-1 Antitrypsin Deficiency",
                "inheritance": "常染色体隐性遗传",
                "gene": "SERPINA1",
                "prevalence": "1/2000-1/5000",
                "age_of_onset": "任何年龄",
                "key_symptoms": [
                    "早发肺气肿",
                    "肝病",
                    "新生儿黄疸",
                    "胰腺炎"
                ],
                "diagnostic_tests": [
                    "AAT 水平检测",
                    "AAT 表型分析",
                    "SERPINA1 基因检测",
                    "肺功能检查"
                ],
                "treatment": [
                    "AAT 替代治疗",
                    "戒烟",
                    "肺移植",
                    "肝移植"
                ]
            }
        }
    
    def search_by_name(self, disease_name: str) -> List[Dict]:
        """
        按疾病名称搜索
        
        Args:
            disease_name: 疾病名称（中英文均可）
        
        Returns:
            匹配的疾病信息
        """
        results = []
        disease_lower = disease_name.lower()
        
        for disease_id, disease_info in self.rare_disease_db.items():
            if (disease_lower in disease_info["name_cn"].lower() or
                disease_lower in disease_info["name_en"].lower() or
                disease_lower in disease_id.lower()):
                results.append({
                    "disease_id": disease_id,
                    **disease_info
                })
        
        return results
    
    def search_by_symptom(self, symptom: str) -> List[Dict]:
        """
        按症状搜索相关疾病
        
        Args:
            symptom: 症状名称
        
        Returns:
            相关疾病列表
        """
        results = []
        symptom_lower = symptom.lower()
        
        for disease_id, disease_info in self.rare_disease_db.items():
            # 检查症状是否匹配
            for key_symptom in disease_info["key_symptoms"]:
                if symptom_lower in key_symptom.lower():
                    results.append({
                        "disease_id": disease_id,
                        "disease_name": disease_info["name_cn"],
                        "matching_symptom": key_symptom,
                        "other_symptoms": disease_info["key_symptoms"]
                    })
                    break
        
        return results
    
    def search_by_gene(self, gene: str) -> List[Dict]:
        """
        按基因搜索相关疾病
        
        Args:
            gene: 基因名称
        
        Returns:
            相关疾病列表
        """
        results = []
        gene_upper = gene.upper()
        
        for disease_id, disease_info in self.rare_disease_db.items():
            if gene_upper in disease_info["gene"].upper():
                results.append({
                    "disease_id": disease_id,
                    "disease_name": disease_info["name_cn"],
                    "gene": disease_info["gene"],
                    "inheritance": disease_info["inheritance"]
                })
        
        return results
    
    def get_disease_details(self, disease_id: str) -> Optional[Dict]:
        """
        获取疾病详细信息
        
        Args:
            disease_id: 疾病 ID
        
        Returns:
            疾病详细信息
        """
        return self.rare_disease_db.get(disease_id)
    
    def get_differential_diagnosis(self, symptoms: List[str]) -> List[Dict]:
        """
        根据症状生成鉴别诊断
        
        Args:
            symptoms: 症状列表
        
        Returns:
            鉴别诊断列表（按匹配度排序）
        """
        diagnosis_scores = {}
        
        for disease_id, disease_info in self.rare_disease_db.items():
            score = 0
            matched_symptoms = []
            
            for symptom in symptoms:
                symptom_lower = symptom.lower()
                for key_symptom in disease_info["key_symptoms"]:
                    if symptom_lower in key_symptom.lower():
                        score += 1
                        matched_symptoms.append(key_symptom)
                        break
            
            if score > 0:
                diagnosis_scores[disease_id] = {
                    "disease_id": disease_id,
                    "disease_name": disease_info["name_cn"],
                    "score": score,
                    "matched_symptoms": matched_symptoms,
                    "total_symptoms": len(disease_info["key_symptoms"]),
                    "match_ratio": score / len(disease_info["key_symptoms"])
                }
        
        # 按匹配度排序
        sorted_diagnosis = sorted(
            diagnosis_scores.values(),
            key=lambda x: (x["score"], x["match_ratio"]),
            reverse=True
        )
        
        return sorted_diagnosis
