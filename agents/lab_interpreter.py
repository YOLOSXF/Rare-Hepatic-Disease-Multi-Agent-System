"""
检验解读 Agent
负责解读肝功能、免疫学、生化学检验结果，识别罕见病线索
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from enum import Enum
import math
from loguru import logger

from .base_agent import BaseAgent, AgentConfig, AgentResponse


class LiverInjuryPattern(str, Enum):
    """肝损伤模式"""
    HEPATOCELLULAR = "hepatocellular"  # 肝细胞损伤型
    CHOLESTATIC = "cholestatic"  # 胆汁淤积型
    MIXED = "mixed"  # 混合型
    ISOLATED_BILIRUBIN = "isolated_bilirubin"  # 单纯胆红素升高
    ISOLATED_ENZYME = "isolated_enzyme"  # 单纯酶学升高


class LabInterpreterConfig(AgentConfig):
    """检验解读 Agent 配置"""
    name: str = "lab_interpreter"
    enable_rare_disease_screening: bool = True
    critical_value_alert: bool = True


class LabInterpretation(BaseModel):
    """检验解读结果"""
    pattern: Optional[str]
    severity: str  # mild/moderate/severe/critical
    abnormal_findings: List[Dict]
    rare_disease_clues: List[Dict]
    calculated_scores: Dict
    recommended_followup: List[str]


class LabInterpreterAgent(BaseAgent):
    """
    检验解读 Agent
    
    核心功能：
    1. 识别异常检验指标
    2. 判断肝损伤模式（肝细胞型/胆汁淤积型/混合型）
    3. 罕见病线索识别
    4. 临床评分计算（FIB-4、Child-Pugh 等）
    """
    
    def __init__(self, config: Optional[LabInterpreterConfig] = None):
        super().__init__(config or LabInterpreterConfig())
        self.config: LabInterpreterConfig = config or LabInterpreterConfig()
        
        # 检验参考范围
        self.reference_ranges = {
            'ALT': {'unit': 'U/L', 'lower': 0, 'upper': 40, 'critical_upper': 500},
            'AST': {'unit': 'U/L', 'lower': 0, 'upper': 40, 'critical_upper': 500},
            'ALP': {'unit': 'U/L', 'lower': 40, 'upper': 125, 'critical_upper': 500},
            'GGT': {'unit': 'U/L', 'lower': 0, 'upper': 60, 'critical_upper': 300},
            'TBil': {'unit': 'μmol/L', 'lower': 3.4, 'upper': 20.5, 'critical_upper': 171},
            'DBil': {'unit': 'μmol/L', 'lower': 0, 'upper': 6.8, 'critical_upper': 85},
            'Albumin': {'unit': 'g/L', 'lower': 35, 'upper': 55, 'critical_lower': 28},
            'PT': {'unit': '秒', 'lower': 11, 'upper': 14, 'critical_upper': 20},
            'INR': {'unit': '', 'lower': 0.8, 'upper': 1.2, 'critical_upper': 2.0},
            'Platelet': {'unit': '×10^9/L', 'lower': 100, 'upper': 300, 'critical_lower': 50},
            'AFP': {'unit': 'ng/mL', 'lower': 0, 'upper': 20, 'critical_upper': 400},
            # 罕见病相关
            'Ceruloplasmin': {'unit': 'g/L', 'lower': 0.20, 'upper': 0.60, 'critical_lower': 0.10},
            'IgG': {'unit': 'g/L', 'lower': 7.0, 'upper': 16.0, 'critical_upper': 20},
            'Ferritin': {'unit': 'μg/L', 'lower': 30, 'upper': 300, 'critical_upper': 1000},
            'AAT': {'unit': 'g/L', 'lower': 0.8, 'upper': 2.0, 'critical_lower': 0.5},
        }
        
        # 危急值标准
        self.critical_values = {
            'ALT': {'critical': 500, 'action': '排查急性肝损伤'},
            'TBil': {'critical': 171, 'action': '排查急性肝衰竭'},
            'INR': {'critical': 2.0, 'action': '凝血功能障碍，紧急评估'},
            'Platelet': {'critical': 50, 'action': '血小板减少，排查脾亢'},
            'Ceruloplasmin': {'critical': 0.10, 'action': '高度怀疑 Wilson 病'}
        }
    
    @property
    def name(self) -> str:
        return "lab_interpreter"
    
    async def execute(self, input_data: Dict[str, Any]) -> AgentResponse:
        """
        执行检验解读
        
        Args:
            input_data: 检验结果字典
        
        Returns:
            AgentResponse: 解读结果
        """
        try:
            lab_results = input_data.get('lab_results', {})
            patient_age = input_data.get('age')
            
            # 1. 识别异常指标
            abnormal_findings = self._identify_abnormalities(lab_results)
            
            # 2. 判断损伤模式
            pattern = self._determine_pattern(lab_results)
            
            # 3. 评估严重程度
            severity = self._assess_severity(lab_results, pattern)
            
            # 4. 罕见病线索识别
            rare_disease_clues = []
            if self.config.enable_rare_disease_screening:
                rare_disease_clues = self._identify_rare_disease_clues(lab_results)
            
            # 5. 计算临床评分
            calculated_scores = self._calculate_scores(lab_results, patient_age)
            
            # 6. 生成随访建议
            recommended_followup = self._generate_followup(
                lab_results, pattern, rare_disease_clues, severity
            )
            
            # 构建结果
            result = LabInterpretation(
                pattern=pattern.value if pattern else None,
                severity=severity,
                abnormal_findings=abnormal_findings,
                rare_disease_clues=rare_disease_clues,
                calculated_scores=calculated_scores,
                recommended_followup=recommended_followup
            )
            
            return self._create_response(
                success=True,
                data=result.dict(),
                metadata={
                    "abnormal_count": len(abnormal_findings),
                    "rare_clues_count": len(rare_disease_clues),
                    "severity": severity
                }
            )
            
        except Exception as e:
            logger.error(f"Lab interpretation failed: {e}")
            return self._create_response(
                success=False,
                error=str(e)
            )
    
    def _identify_abnormalities(self, lab_results: Dict) -> List[Dict]:
        """识别异常指标"""
        abnormalities = []
        
        for test_name, value in lab_results.items():
            if test_name not in self.reference_ranges or not isinstance(value, (int, float)):
                continue
            
            ref = self.reference_ranges[test_name]
            
            if value > ref['upper']:
                ratio = value / ref['upper']
                severity = 'mild' if ratio < 2 else ('moderate' if ratio < 5 else 'severe')
                abnormalities.append({
                    'test': test_name,
                    'value': value,
                    'unit': ref['unit'],
                    'reference': f"{ref['lower']}-{ref['upper']}",
                    'direction': 'high',
                    'severity': severity,
                    'ratio': round(ratio, 2)
                })
            elif value < ref['lower'] and ref['lower'] > 0:
                ratio = value / ref['lower']
                severity = 'mild' if ratio > 0.8 else ('moderate' if ratio > 0.5 else 'severe')
                abnormalities.append({
                    'test': test_name,
                    'value': value,
                    'unit': ref['unit'],
                    'reference': f"{ref['lower']}-{ref['upper']}",
                    'direction': 'low',
                    'severity': severity,
                    'ratio': round(ratio, 2)
                })
        
        return abnormalities
    
    def _determine_pattern(self, lab_results: Dict) -> Optional[LiverInjuryPattern]:
        """
        判断肝损伤模式
        
        基于 R 值 = (ALT/ALT_ULN) / (ALP/ALP_ULN)
        - R ≥ 5: 肝细胞损伤型
        - R ≤ 2: 胆汁淤积型
        - 2 < R < 5: 混合型
        """
        alt = lab_results.get('ALT', 0)
        alp = lab_results.get('ALP', 0)
        tbil = lab_results.get('TBil', 0)
        
        alt_uln = self.reference_ranges['ALT']['upper']
        alp_uln = self.reference_ranges['ALP']['upper']
        
        if alt == 0 and alp == 0:
            return LiverInjuryPattern.ISOLATED_BILIRUBIN if tbil > 20.5 else None
        
        if alp <= alp_uln:
            r_value = float('inf')
        else:
            r_value = (alt / alt_uln) / (alp / alp_uln)
        
        if r_value >= 5:
            return LiverInjuryPattern.HEPATOCELLULAR
        elif r_value <= 2:
            return LiverInjuryPattern.CHOLESTATIC
        else:
            return LiverInjuryPattern.MIXED
    
    def _assess_severity(self, lab_results: Dict, pattern: Optional[LiverInjuryPattern]) -> str:
        """评估严重程度"""
        # 检查危急值
        for test, critical in self.critical_values.items():
            value = lab_results.get(test)
            if value is None:
                continue
            
            if test in ['ALT', 'AST', 'ALP', 'GGT', 'TBil']:
                if value >= critical['critical']:
                    return 'critical'
            elif test == 'INR':
                if value >= critical['critical']:
                    return 'critical'
            elif test == 'Platelet':
                if value <= critical['critical']:
                    return 'critical'
            elif test == 'Ceruloplasmin':
                if value <= critical['critical']:
                    return 'critical'
        
        # 基于损伤模式评估
        if pattern == LiverInjuryPattern.HEPATOCELLULAR:
            alt = lab_results.get('ALT', 0)
            if alt > 500:
                return 'severe'
            elif alt > 200:
                return 'moderate'
        
        elif pattern == LiverInjuryPattern.CHOLESTATIC:
            tbil = lab_results.get('TBil', 0)
            if tbil > 171:
                return 'severe'
            elif tbil > 85:
                return 'moderate'
        
        return 'mild'
    
    def _identify_rare_disease_clues(self, lab_results: Dict) -> List[Dict]:
        """识别罕见病线索"""
        clues = []
        
        # Wilson 病线索
        ceruloplasmin = lab_results.get('Ceruloplasmin')
        if ceruloplasmin:
            if ceruloplasmin < 0.20:
                significance = '高度提示 Wilson 病' if ceruloplasmin < 0.10 else '提示 Wilson 病'
                clues.append({
                    'disease': 'Wilson_Disease',
                    'finding': '铜蓝蛋白降低',
                    'value': f"{ceruloplasmin} g/L",
                    'significance': significance,
                    'next_steps': ['24 小时尿铜', '裂隙灯检查 K-F 环', 'ATP7B 基因检测']
                })
        
        # AIH 线索
        igg = lab_results.get('IgG')
        ana = lab_results.get('ANA')
        sma = lab_results.get('SMA')
        
        if igg and igg > 16:
            clue = {
                'disease': 'Autoimmune_Hepatitis',
                'finding': '高球蛋白血症',
                'value': f"{igg} g/L",
                'significance': '提示自身免疫性肝病',
                'next_steps': ['自身抗体谱', '肝活检']
            }
            if ana == 'positive' or sma == 'positive':
                clue['significance'] = '高度提示 AIH'
                clue['supporting_evidence'] = f"ANA: {ana}, SMA: {sma}"
            clues.append(clue)
        
        # 血色病线索
        ferritin = lab_results.get('Ferritin')
        transferrin_sat = lab_results.get('Transferrin_Saturation')
        
        if ferritin and ferritin > 300:
            clue = {
                'disease': 'Hereditary_Hemochromatosis',
                'finding': '铁蛋白升高',
                'value': f"{ferritin} μg/L",
                'significance': '提示铁过载',
                'next_steps': ['转铁蛋白饱和度', 'HFE 基因检测']
            }
            if transferrin_sat and transferrin_sat > 0.45:
                clue['significance'] = '高度提示遗传性血色病'
                clue['next_steps'].append('肝脏 MRI T2* 评估铁沉积')
            clues.append(clue)
        
        # α1-抗胰蛋白酶缺乏症线索
        aat = lab_results.get('AAT')
        if aat and aat < 0.8:
            clues.append({
                'disease': 'Alpha1_Antitrypsin_Deficiency',
                'finding': 'α1-抗胰蛋白酶降低',
                'value': f"{aat} g/L",
                'significance': '提示 AAT 缺乏症',
                'next_steps': ['AAT 表型分析', 'SERPINA1 基因检测', '肺功能检查']
            })
        
        # PBC 线索
        ama = lab_results.get('AMA')
        alp = lab_results.get('ALP')
        
        if ama == 'positive':
            clue = {
                'disease': 'Primary_Biliary_Cholangitis',
                'finding': 'AMA 阳性',
                'significance': '高度提示 PBC',
                'next_steps': ['AMA-M2', '肝脏超声', '肝活检']
            }
            if alp and alp > 125:
                clue['supporting_evidence'] = f"ALP: {alp} U/L"
            clues.append(clue)
        
        return clues
    
    def _calculate_scores(self, lab_results: Dict, patient_age: Optional[int]) -> Dict:
        """计算临床评分"""
        scores = {}
        
        # FIB-4 评分
        fib4 = self._calculate_fib4(lab_results, patient_age)
        if fib4:
            scores['FIB4'] = {
                'value': fib4,
                'interpretation': self._interpret_fib4(fib4)
            }
        
        # Child-Pugh 评分（如有相关数据）
        child_pugh = self._calculate_child_pugh(lab_results)
        if child_pugh:
            scores['Child_Pugh'] = child_pugh
        
        return scores
    
    def _calculate_fib4(self, lab_results: Dict, age: Optional[int]) -> Optional[float]:
        """计算 FIB-4 评分"""
        ast = lab_results.get('AST')
        alt = lab_results.get('ALT')
        platelets = lab_results.get('Platelet')
        
        if not all([age, ast, alt, platelets]):
            return None
        
        # FIB-4 = (年龄 × AST) / (血小板 × √ALT)
        try:
            fib4 = (age * ast) / (platelets * math.sqrt(alt)) if alt > 0 else None
            return round(fib4, 2) if fib4 else None
        except (ZeroDivisionError, ValueError):
            return None
    
    def _interpret_fib4(self, fib4: float) -> str:
        """解读 FIB-4 评分"""
        if fib4 < 1.30:
            return "低风险（排除显著纤维化，阴性预测值 90%）"
        elif fib4 <= 2.67:
            return "中风险（需进一步评估，建议 FibroScan 或专科就诊）"
        else:
            return "高风险（提示进展期纤维化，阳性预测值 65%，建议转诊）"
    
    def _calculate_child_pugh(self, lab_results: Dict) -> Optional[Dict]:
        """计算 Child-Pugh 评分"""
        tbil = lab_results.get('TBil')
        albumin = lab_results.get('Albumin')
        inr = lab_results.get('INR')
        
        if not all([tbil, albumin, inr]):
            return None
        
        score = 0
        
        # 胆红素评分
        if tbil < 34:
            score += 1
        elif tbil <= 51:
            score += 2
        else:
            score += 3
        
        # 白蛋白评分
        if albumin > 35:
            score += 1
        elif albumin >= 28:
            score += 2
        else:
            score += 3
        
        # INR 评分
        if inr < 1.7:
            score += 1
        elif inr <= 2.3:
            score += 2
        else:
            score += 3
        
        # 腹水和肝性脑病（需要临床评估）
        ascites = lab_results.get('ascites', 'none')
        encephalopathy = lab_results.get('encephalopathy', 'none')
        
        if ascites == 'mild':
            score += 2
        elif ascites == 'moderate_severe':
            score += 3
        
        if encephalopathy == 'grade_1_2':
            score += 2
        elif encephalopathy == 'grade_3_4':
            score += 3
        
        # 分级
        if score <= 6:
            grade = 'A'
            description = '代偿期肝硬化'
            survival = '100%'
        elif score <= 9:
            grade = 'B'
            description = '失代偿期肝硬化'
            survival = '80%'
        else:
            grade = 'C'
            description = '严重失代偿期肝硬化'
            survival = '45%'
        
        return {
            'score': score,
            'grade': grade,
            'description': description,
            'one_year_survival': survival
        }
    
    def _generate_followup(
        self,
        lab_results: Dict,
        pattern: Optional[LiverInjuryPattern],
        rare_disease_clues: List[Dict],
        severity: str
    ) -> List[str]:
        """生成随访建议"""
        followup = []
        
        # 危急值处理
        if severity == 'critical':
            followup.append("⚠️ 危急值，建议立即就诊急诊科")
            followup.append("完善凝血功能、血氨、动脉血气分析")
            followup.append("排查急性肝衰竭")
            return followup
        
        # 基于损伤模式
        if pattern == LiverInjuryPattern.HEPATOCELLULAR:
            followup.append("排查病毒性肝炎（乙肝两对半、丙肝抗体）")
            followup.append("询问用药史，排查药物性肝损伤")
            followup.append("腹部超声检查")
        
        elif pattern == LiverInjuryPattern.CHOLESTATIC:
            followup.append("排查胆道梗阻（MRCP 或 ERCP）")
            followup.append("排查自身免疫性胆汁淤积性肝病（AMA、AMA-M2）")
            followup.append("腹部超声或 CT 检查")
        
        # 基于罕见病线索
        if rare_disease_clues:
            followup.append("⚠️ 发现罕见病线索，建议转诊肝病专科")
            for clue in rare_disease_clues:
                for test in clue['next_steps'][:2]:
                    followup.append(f"排查{clue['disease']}: {test}")
        
        # 常规建议
        if severity == 'mild':
            followup.append("生活方式干预（戒酒、减重、避免肝毒性药物）")
            followup.append("1-3 个月复查肝功能")
        
        return followup
