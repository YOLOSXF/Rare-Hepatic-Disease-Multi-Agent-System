"""
诊疗指南搜索工具
检索中华医学会、AASLD、EASL 等肝病诊疗指南
"""

from typing import List, Dict, Optional
from loguru import logger


class GuidelineSearchTool:
    """
    诊疗指南搜索工具
    
    提供肝病相关诊疗指南检索
    """
    
    def __init__(self):
        """初始化工具"""
        # 内置指南数据库（简化版，实际应该连接数据库）
        self.guidelines_db = self._load_guidelines()
    
    def _load_guidelines(self) -> Dict:
        """加载指南数据库"""
        return {
            "Wilson_Disease": [
                {
                    "title": "中华医学会肝豆状核变性诊疗指南",
                    "year": 2022,
                    "organization": "中华医学会肝病学分会",
                    "url": "http://www.cma.org.cn/",
                    "key_points": [
                        "铜蓝蛋白<0.20 g/L 支持诊断",
                        "24 小时尿铜>100 μg 有诊断价值",
                        "K-F 环阳性是重要体征",
                        "ATP7B 基因检测可确诊"
                    ]
                },
                {
                    "title": "EASL Clinical Practice Guidelines: Wilson disease",
                    "year": 2012,
                    "organization": "European Association for the Study of the Liver",
                    "url": "https://www.journal-of-hepatology.eu/",
                    "key_points": [
                        "Leipzig 评分系统用于诊断",
                        "青霉胺是首选治疗",
                        "终身治疗是必要的"
                    ]
                }
            ],
            "Autoimmune_Hepatitis": [
                {
                    "title": "自身免疫性肝炎诊断和治疗指南",
                    "year": 2021,
                    "organization": "中华医学会肝病学分会",
                    "url": "http://www.cma.org.cn/",
                    "key_points": [
                        "ANA/SMA/LKM-1 阳性支持诊断",
                        "IgG 升高是重要指标",
                        "肝活检显示界面性肝炎",
                        "糖皮质激素是首选治疗"
                    ]
                },
                {
                    "title": "AASLD Practice Guidance: Autoimmune Hepatitis",
                    "year": 2019,
                    "organization": "American Association for the Study of Liver Diseases",
                    "url": "https://www.aasld.org/",
                    "key_points": [
                        "简化诊断标准便于临床应用",
                        "泼尼松联合硫唑嘌呤是标准治疗",
                        "治疗目标是生化缓解和组织学改善"
                    ]
                }
            ],
            "Hereditary_Hemochromatosis": [
                {
                    "title": "遗传性血色病诊断和治疗专家共识",
                    "year": 2020,
                    "organization": "中国医师协会",
                    "url": "http://www.cmda.net/",
                    "key_points": [
                        "转铁蛋白饱和度>45% 筛查阳性",
                        "铁蛋白>300 μg/L 提示铁过载",
                        "HFE 基因 C282Y 突变是主要病因",
                        "静脉放血是标准治疗"
                    ]
                }
            ],
            "Primary_Biliary_Cholangitis": [
                {
                    "title": "原发性胆汁性胆管炎诊断和治疗指南",
                    "year": 2021,
                    "organization": "中华医学会肝病学分会",
                    "url": "http://www.cma.org.cn/",
                    "key_points": [
                        "AMA/AMA-M2 阳性是诊断标志",
                        "ALP 升高是主要生化异常",
                        "熊去氧胆酸是一线治疗",
                        "奥贝胆酸是二线选择"
                    ]
                },
                {
                    "title": "EASL Clinical Practice Guidelines: PBC",
                    "year": 2017,
                    "organization": "European Association for the Study of the Liver",
                    "url": "https://www.journal-of-hepatology.eu/",
                    "key_points": [
                        "胆汁淤积生化证据持续 6 个月以上",
                        "AMA 阳性率>95%",
                        "UDCA 13-15 mg/kg/d 是标准剂量"
                    ]
                }
            ]
        }
    
    def search(self, disease: str) -> List[Dict]:
        """
        搜索相关指南
        
        Args:
            disease: 疾病名称
        
        Returns:
            指南列表
        """
        guidelines = self.guidelines_db.get(disease, [])
        
        if not guidelines:
            # 尝试模糊匹配
            guidelines = self._fuzzy_match(disease)
        
        return guidelines
    
    def _fuzzy_match(self, disease: str) -> List[Dict]:
        """模糊匹配指南"""
        matched = []
        disease_lower = disease.lower()
        
        for key, guidelines in self.guidelines_db.items():
            if disease_lower in key.lower() or key.lower() in disease_lower:
                matched.extend(guidelines)
        
        return matched
    
    def get_diagnostic_criteria(self, disease: str) -> Dict:
        """
        获取诊断标准
        
        Args:
            disease: 疾病名称
        
        Returns:
            诊断标准
        """
        criteria_map = {
            "Wilson_Disease": {
                "major_criteria": [
                    "铜蓝蛋白降低 (<0.20 g/L)",
                    "K-F 环阳性",
                    "24 小时尿铜升高 (>100 μg/24h)"
                ],
                "minor_criteria": [
                    "神经精神症状",
                    "肝功能异常",
                    "Coombs 阴性溶血性贫血",
                    "家族史"
                ],
                "scoring_system": "Leipzig 评分"
            },
            "Autoimmune_Hepatitis": {
                "major_criteria": [
                    "自身抗体阳性 (ANA/SMA/LKM-1)",
                    "IgG 升高 (>1.1×ULN)",
                    "肝活检显示界面性肝炎"
                ],
                "minor_criteria": [
                    "女性",
                    "合并其他自身免疫病",
                    "HLA-DR3/DR4 阳性"
                ],
                "scoring_system": "IAIHG 评分"
            },
            "Hereditary_Hemochromatosis": {
                "major_criteria": [
                    "转铁蛋白饱和度升高 (>45%)",
                    "铁蛋白升高 (>300 μg/L)",
                    "HFE 基因突变"
                ],
                "minor_criteria": [
                    "皮肤色素沉着",
                    "糖尿病",
                    "关节痛",
                    "家族史"
                ]
            },
            "Primary_Biliary_Cholangitis": {
                "major_criteria": [
                    "AMA/AMA-M2 阳性",
                    "胆汁淤积生化证据 (ALP 升高)",
                    "肝活检显示胆管破坏"
                ],
                "minor_criteria": [
                    "中年女性",
                    "皮肤瘙痒",
                    "IgM 升高",
                    "合并其他自身免疫病"
                ]
            }
        }
        
        return criteria_map.get(disease, {})
    
    def get_treatment_recommendations(self, disease: str) -> List[Dict]:
        """
        获取治疗建议
        
        Args:
            disease: 疾病名称
        
        Returns:
            治疗建议列表
        """
        treatment_map = {
            "Wilson_Disease": [
                {
                    "line": "一线",
                    "treatment": "青霉胺",
                    "dose": "250-500mg, 每日 3-4 次",
                    "notes": "需补充维生素 B6"
                },
                {
                    "line": "二线",
                    "treatment": "曲恩汀",
                    "dose": "250-500mg, 每日 2-3 次",
                    "notes": "耐受性更好"
                },
                {
                    "line": "维持",
                    "treatment": "锌剂",
                    "dose": "50mg 元素锌，每日 2-3 次",
                    "notes": "减少铜吸收"
                }
            ],
            "Autoimmune_Hepatitis": [
                {
                    "line": "诱导",
                    "treatment": "泼尼松",
                    "dose": "30-60mg/d，逐渐减量",
                    "notes": "监测副作用"
                },
                {
                    "line": "维持",
                    "treatment": "硫唑嘌呤",
                    "dose": "1-2mg/kg/d",
                    "notes": "检测 TPMT 活性"
                }
            ]
        }
        
        return treatment_map.get(disease, [])
