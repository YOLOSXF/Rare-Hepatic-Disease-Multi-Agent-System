"""
临床评分系统
提供常用肝病临床评分计算
"""

from typing import Dict, Optional
import math


class ClinicalScoringSystem:
    """
    临床评分系统
    
    提供以下评分：
    - FIB-4
    - NAFLD 纤维化评分
    - Child-Pugh
    - MELD
    - RUCAM
    """
    
    @staticmethod
    def calculate_fib4(age: int, ast: float, alt: float, platelets: float) -> Optional[float]:
        """
        计算 FIB-4 评分
        
        FIB-4 = (年龄 × AST) / (血小板 × √ALT)
        """
        if not all([age, ast, alt, platelets]) or alt <= 0:
            return None
        
        fib4 = (age * ast) / (platelets * math.sqrt(alt))
        return round(fib4, 2)
    
    @staticmethod
    def interpret_fib4(fib4: float) -> Dict:
        """解读 FIB-4 评分"""
        if fib4 < 1.30:
            return {
                'risk': 'low',
                'description': '低风险（排除显著纤维化）',
                'npv': '90%',
                'recommendation': '基层随访'
            }
        elif fib4 <= 2.67:
            return {
                'risk': 'indeterminate',
                'description': '中风险（需进一步评估）',
                'recommendation': 'FibroScan 或专科就诊'
            }
        else:
            return {
                'risk': 'high',
                'description': '高风险（提示进展期纤维化）',
                'ppv': '65%',
                'recommendation': '转诊肝病专科'
            }
    
    @staticmethod
    def calculate_child_pugh(
        tbil: float,
        albumin: float,
        inr: float,
        ascites: str = 'none',
        encephalopathy: str = 'none'
    ) -> Optional[Dict]:
        """
        计算 Child-Pugh 评分
        
        参数：
        - tbil: 总胆红素 (μmol/L)
        - albumin: 白蛋白 (g/L)
        - inr: 国际标准化比值
        - ascites: 腹水 (none/mild/moderate_severe)
        - encephalopathy: 肝性脑病 (none/grade_1_2/grade_3_4)
        """
        if not all([tbil, albumin, inr]):
            return None
        
        score = 0
        
        # 胆红素
        if tbil < 34:
            score += 1
        elif tbil <= 51:
            score += 2
        else:
            score += 3
        
        # 白蛋白
        if albumin > 35:
            score += 1
        elif albumin >= 28:
            score += 2
        else:
            score += 3
        
        # INR
        if inr < 1.7:
            score += 1
        elif inr <= 2.3:
            score += 2
        else:
            score += 3
        
        # 腹水
        ascites_scores = {'none': 1, 'mild': 2, 'moderate_severe': 3}
        score += ascites_scores.get(ascites, 1)
        
        # 肝性脑病
        encephalopathy_scores = {'none': 1, 'grade_1_2': 2, 'grade_3_4': 3}
        score += encephalopathy_scores.get(encephalopathy, 1)
        
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
    
    @staticmethod
    def calculate_meld(
        tbil: float,
        inr: float,
        creatinine: float,
        dialysis: bool = False
    ) -> Optional[float]:
        """
        计算 MELD 评分
        
        MELD = 3.78×ln(胆红素) + 11.2×ln(INR) + 9.57×ln(肌酐) + 6.43
        """
        if not all([tbil, inr, creatinine]):
            return None
        
        # 最小值限制
        tbil = max(tbil, 1)
        inr = max(inr, 1)
        creatinine = max(creatinine, 1)
        
        # 透析患者肌酐特殊处理
        if dialysis:
            creatinine = 4.0
        
        import math
        meld = (
            3.78 * math.log(tbil) +
            11.2 * math.log(inr) +
            9.57 * math.log(creatinine) +
            6.43
        )
        
        return round(min(40, max(6, meld)), 0)
