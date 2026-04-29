import sys
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.preprocessor import DataPreprocessor
from core.data_assessor import DataCompletenessAssessor
from core.triage import IntelligentTriage
from loguru import logger


@dataclass
class L1TestResult:
    """L1层测试结果"""
    case_id: str
    case_name: str
    category: str
    
    expected_trigger_incomplete: bool
    actual_trigger_incomplete: bool
    expected_missing_fields: List[str]
    actual_missing_fields: List[str]
    expected_score_range: str
    actual_score: float
    
    is_correct: bool
    match_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class L2TestResult:
    """L2层测试结果"""
    case_id: str
    case_name: str
    category: str
    
    expected_path: str
    actual_path: str
    expected_diagnosis_keywords: List[str]
    actual_diagnosis: str
    expected_is_rare_alert: bool
    actual_is_rare_alert: bool
    expected_confidence_levels: List[str]
    actual_confidence_level: str
    
    is_correct: bool
    match_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseTestResult:
    """单个病例测试结果"""
    case_id: str
    case_name: str
    category: str
    patient_data: Dict[str, Any]
    
    l1_result: Optional[L1TestResult] = None
    l2_result: Optional[L2TestResult] = None
    
    overall_correct: bool = False
    execution_time_ms: int = 0


class PatientCaseTester:
    """患者病例测试执行器"""
    
    def __init__(self, results_dir: str = "tests/results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        self.preprocessor = DataPreprocessor()
        self.assessor = DataCompletenessAssessor()
        self.triage = IntelligentTriage(rules_dir="rules")
        
        self.test_results: List[CaseTestResult] = []
    
    def load_cases(self, json_file: str) -> List[Dict]:
        """加载患者病例"""
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('test_cases', [])
    
    def test_l1_layer(self, patient_data: Dict, expected: Dict) -> L1TestResult:
        """执行L1层测试"""
        preprocess_result = self.preprocessor.preprocess(patient_data)
        assessment = self.assessor.assess(patient_data)
        
        actual_missing = preprocess_result.missing_values + assessment.missing_critical
        actual_missing = list(set(actual_missing))
        
        expected_trigger = expected.get('should_trigger_incomplete', False)
        expected_missing = expected.get('expected_missing_fields', [])
        expected_score_range = expected.get('expected_completeness_score', '>=0')
        
        actual_trigger = len(actual_missing) > 0 or assessment.score < 0.7
        actual_score = assessment.score
        
        is_correct = True
        match_details = {}
        
        if expected_trigger != actual_trigger:
            is_correct = False
            match_details['trigger_mismatch'] = {
                'expected': expected_trigger,
                'actual': actual_trigger
            }
        
        for field in expected_missing:
            field_found = any(field.lower() in m.lower() for m in actual_missing)
            if not field_found and expected_trigger:
                is_correct = False
                match_details.setdefault('missing_field_mismatch', [])
                match_details['missing_field_mismatch'].append(field)
        
        if '>=' in expected_score_range:
            threshold = float(expected_score_range.replace('>=', ''))
            if actual_score < threshold:
                is_correct = False
                match_details['score_below_threshold'] = {
                    'expected': f">={threshold}",
                    'actual': actual_score
                }
        elif '<' in expected_score_range:
            threshold = float(expected_score_range.replace('<', ''))
            if actual_score >= threshold:
                is_correct = False
                match_details['score_above_threshold'] = {
                    'expected': f"<{threshold}",
                    'actual': actual_score
                }
        
        return L1TestResult(
            case_id="",
            case_name="",
            category="",
            expected_trigger_incomplete=expected_trigger,
            actual_trigger_incomplete=actual_trigger,
            expected_missing_fields=expected_missing,
            actual_missing_fields=actual_missing,
            expected_score_range=expected_score_range,
            actual_score=actual_score,
            is_correct=is_correct,
            match_details=match_details
        )
    
    async def test_l2_layer(self, patient_data: Dict, expected: Dict) -> L2TestResult:
        """执行L2层测试"""
        triage_result = await self.triage.triage(patient_data)
        
        expected_path = expected.get('expected_path', 'uncertain')
        expected_keywords = expected.get('expected_diagnosis_contains', [])
        expected_rare = expected.get('expected_is_rare_alert', False)
        expected_conf_levels = expected.get('expected_confidence_level', ['low'])
        
        actual_path = triage_result.path
        actual_diagnosis = triage_result.diagnosis or ""
        actual_rare = triage_result.is_rare_disease_alert
        actual_conf_level = triage_result.confidence_level
        
        is_correct = True
        match_details = {}
        
        if expected_path != actual_path:
            is_correct = False
            match_details['path_mismatch'] = {
                'expected': expected_path,
                'actual': actual_path
            }
        
        if expected_keywords:
            keyword_found = any(kw.lower() in actual_diagnosis.lower() for kw in expected_keywords)
            if not keyword_found and actual_path not in ['uncertain', 'insufficient_data']:
                is_correct = False
                match_details['diagnosis_mismatch'] = {
                    'expected_keywords': expected_keywords,
                    'actual_diagnosis': actual_diagnosis
                }
        
        if expected_rare != actual_rare:
            is_correct = False
            match_details['rare_alert_mismatch'] = {
                'expected': expected_rare,
                'actual': actual_rare
            }
        
        if actual_conf_level not in expected_conf_levels:
            is_correct = False
            match_details['confidence_mismatch'] = {
                'expected': expected_conf_levels,
                'actual': actual_conf_level
            }
        
        return L2TestResult(
            case_id="",
            case_name="",
            category="",
            expected_path=expected_path,
            actual_path=actual_path,
            expected_diagnosis_keywords=expected_keywords,
            actual_diagnosis=actual_diagnosis,
            expected_is_rare_alert=expected_rare,
            actual_is_rare_alert=actual_rare,
            expected_confidence_levels=expected_conf_levels,
            actual_confidence_level=actual_conf_level,
            is_correct=is_correct,
            match_details=match_details
        )
    
    async def run_test(self, case: Dict) -> CaseTestResult:
        """执行单个病例测试"""
        import time
        start_time = time.time()
        
        case_id = case['case_id']
        case_name = case['case_name']
        category = case['category']
        patient_data = case['patient_data']
        expected = case['expected_results']
        
        result = CaseTestResult(
            case_id=case_id,
            case_name=case_name,
            category=category,
            patient_data=patient_data
        )
        
        l1_result = self.test_l1_layer(patient_data, expected.get('L1', {}))
        l1_result.case_id = case_id
        l1_result.case_name = case_name
        l1_result.category = category
        result.l1_result = l1_result
        
        l2_result = await self.test_l2_layer(patient_data, expected.get('L2', {}))
        l2_result.case_id = case_id
        l2_result.case_name = case_name
        l2_result.category = category
        result.l2_result = l2_result
        
        result.overall_correct = l1_result.is_correct and l2_result.is_correct
        result.execution_time_ms = int((time.time() - start_time) * 1000)
        
        return result
    
    async def run_all_tests(self, cases: List[Dict]) -> List[CaseTestResult]:
        """执行所有测试"""
        results = []
        for i, case in enumerate(cases, 1):
            print(f"执行测试 [{i}/{len(cases)}]: {case['case_id']} - {case['case_name']}")
            result = await self.run_test(case)
            results.append(result)
            
            status = "✅ 通过" if result.overall_correct else "❌ 失败"
            print(f"  {status}")
            if not result.overall_correct:
                if not result.l1_result.is_correct:
                    print(f"    L1层: {result.l1_result.match_details}")
                if not result.l2_result.is_correct:
                    print(f"    L2层: {result.l2_result.match_details}")
        
        self.test_results = results
        return results
    
    def calculate_statistics(self) -> Dict[str, Any]:
        """计算统计数据"""
        total = len(self.test_results)
        if total == 0:
            return {}
        
        overall_correct = sum(1 for r in self.test_results if r.overall_correct)
        l1_correct = sum(1 for r in self.test_results if r.l1_result and r.l1_result.is_correct)
        l2_correct = sum(1 for r in self.test_results if r.l2_result and r.l2_result.is_correct)
        
        categories = {}
        for result in self.test_results:
            cat = result.category
            if cat not in categories:
                categories[cat] = {'total': 0, 'correct': 0}
            categories[cat]['total'] += 1
            if result.overall_correct:
                categories[cat]['correct'] += 1
        
        path_stats = {}
        for result in self.test_results:
            if result.l2_result:
                path = result.l2_result.actual_path
                if path not in path_stats:
                    path_stats[path] = {'total': 0, 'correct': 0}
                path_stats[path]['total'] += 1
                if result.l2_result.is_correct:
                    path_stats[path]['correct'] += 1
        
        return {
            'total_cases': total,
            'overall_correct': overall_correct,
            'overall_accuracy': overall_correct / total,
            'l1_correct': l1_correct,
            'l1_accuracy': l1_correct / total,
            'l2_correct': l2_correct,
            'l2_accuracy': l2_correct / total,
            'by_category': categories,
            'by_path': path_stats,
            'execution_time_ms': sum(r.execution_time_ms for r in self.test_results)
        }
    
    def generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        stats = self.calculate_statistics()
        
        detailed_results = []
        for result in self.test_results:
            detailed_results.append({
                'case_id': result.case_id,
                'case_name': result.case_name,
                'category': result.category,
                'patient_summary': {
                    'age': result.patient_data.get('age'),
                    'gender': result.patient_data.get('gender'),
                    'chief_complaint': result.patient_data.get('chief_complaint')
                },
                'l1_test': {
                    'expected_trigger': result.l1_result.expected_trigger_incomplete,
                    'actual_trigger': result.l1_result.actual_trigger_incomplete,
                    'expected_missing': result.l1_result.expected_missing_fields,
                    'actual_missing': result.l1_result.actual_missing_fields,
                    'completeness_score': result.l1_result.actual_score,
                    'is_correct': result.l1_result.is_correct,
                    'match_details': result.l1_result.match_details
                } if result.l1_result else None,
                'l2_test': {
                    'expected_path': result.l2_result.expected_path,
                    'actual_path': result.l2_result.actual_path,
                    'expected_diagnosis_keywords': result.l2_result.expected_diagnosis_keywords,
                    'actual_diagnosis': result.l2_result.actual_diagnosis,
                    'expected_rare_alert': result.l2_result.expected_is_rare_alert,
                    'actual_rare_alert': result.l2_result.actual_is_rare_alert,
                    'expected_confidence': result.l2_result.expected_confidence_levels,
                    'actual_confidence': result.l2_result.actual_confidence_level,
                    'is_correct': result.l2_result.is_correct,
                    'match_details': result.l2_result.match_details
                } if result.l2_result else None,
                'overall_correct': result.overall_correct,
                'execution_time_ms': result.execution_time_ms
            })
        
        return {
            'report_id': f"RPT-PATIENT-CASES-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'generated_at': datetime.now().isoformat(),
            'statistics': stats,
            'detailed_results': detailed_results
        }
    
    def save_report(self, report: Dict, filename: Optional[str] = None) -> str:
        """保存报告"""
        if filename is None:
            filename = f"patient_case_test_report_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        
        filepath = self.results_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        return str(filepath)
    
    def generate_markdown_report(self, report: Dict) -> str:
        """生成Markdown格式报告"""
        stats = report['statistics']
        
        lines = [
            "# 患者病例分诊测试报告",
            "",
            f"**报告ID**: {report['report_id']}",
            f"**生成时间**: {report['generated_at']}",
            "",
            "## 测试摘要",
            "",
            "| 指标 | 值 |",
            "|------|-----|",
            f"| 总测试病例数 | {stats['total_cases']} |",
            f"| 总体正确数 | {stats['overall_correct']} |",
            f"| **总体正确率** | **{stats['overall_accuracy']:.2%}** |",
            f"| L1层正确数 | {stats['l1_correct']} |",
            f"| L1层正确率 | {stats['l1_accuracy']:.2%} |",
            f"| L2层正确数 | {stats['l2_correct']} |",
            f"| L2层正确率 | {stats['l2_accuracy']:.2%} |",
            f"| 总执行时间 | {stats['execution_time_ms']/1000:.2f}s |",
            "",
            "## 按病例类型统计",
            "",
            "| 类型 | 总数 | 正确 | 正确率 |",
            "|------|------|------|--------|",
        ]
        
        for cat, data in stats['by_category'].items():
            accuracy = data['correct'] / data['total'] if data['total'] > 0 else 0
            lines.append(f"| {cat} | {data['total']} | {data['correct']} | {accuracy:.2%} |")
        
        lines.extend([
            "",
            "## 按分诊路径统计",
            "",
            "| 分诊路径 | 总数 | 正确 | 正确率 |",
            "|----------|------|------|--------|",
        ])
        
        for path, data in stats['by_path'].items():
            accuracy = data['correct'] / data['total'] if data['total'] > 0 else 0
            lines.append(f"| {path} | {data['total']} | {data['correct']} | {accuracy:.2%} |")
        
        lines.extend([
            "",
            "## 详细测试结果",
            "",
        ])
        
        for result in report['detailed_results']:
            status = "✅ 通过" if result['overall_correct'] else "❌ 失败"
            lines.extend([
                f"### {result['case_id']}: {result['case_name']} {status}",
                "",
                f"**类型**: {result['category']}",
                "",
                f"**患者信息**: {result['patient_summary']['age']}岁, {result['patient_summary']['gender']}, 主诉: {result['patient_summary']['chief_complaint']}",
                "",
                "#### L1层测试结果",
                "",
            ])
            
            if result['l1_test']:
                l1 = result['l1_test']
                l1_status = "✅" if l1['is_correct'] else "❌"
                lines.extend([
                    f"- 状态: {l1_status}",
                    f"- 预期触发信息不全: {l1['expected_trigger']}",
                    f"- 实际触发信息不全: {l1['actual_trigger']}",
                    f"- 预期缺失字段: {l1['expected_missing']}",
                    f"- 实际缺失字段: {l1['actual_missing']}",
                    f"- 数据完整度评分: {l1['completeness_score']:.2f}",
                    "",
                ])
                
                if l1['match_details']:
                    lines.append(f"- **差异详情**: `{json.dumps(l1['match_details'], ensure_ascii=False)}`")
                    lines.append("")
            
            lines.extend([
                "#### L2层测试结果",
                "",
            ])
            
            if result['l2_test']:
                l2 = result['l2_test']
                l2_status = "✅" if l2['is_correct'] else "❌"
                lines.extend([
                    f"- 状态: {l2_status}",
                    f"- 预期分诊路径: {l2['expected_path']}",
                    f"- 实际分诊路径: {l2['actual_path']}",
                    f"- 预期诊断关键词: {l2['expected_diagnosis_keywords']}",
                    f"- 实际诊断: {l2['actual_diagnosis']}",
                    f"- 预期罕见病预警: {l2['expected_rare_alert']}",
                    f"- 实际罕见病预警: {l2['actual_rare_alert']}",
                    f"- 预期置信度: {l2['expected_confidence']}",
                    f"- 实际置信度: {l2['actual_confidence']}",
                    "",
                ])
                
                if l2['match_details']:
                    lines.append(f"- **差异详情**: `{json.dumps(l2['match_details'], ensure_ascii=False)}`")
                    lines.append("")
        
        content = "\n".join(lines)
        
        filename = f"patient_case_test_report_{datetime.now().strftime('%Y%m%d%H%M%S')}.md"
        filepath = self.results_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return str(filepath)


async def main():
    """主函数"""
    print("\n" + "="*70)
    print("患者病例分诊测试系统")
    print("="*70)
    print(f"测试开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")
    
    tester = PatientCaseTester(results_dir="tests/results")
    
    cases_file = Path(__file__).parent / "patient_cases_suite.json"
    print(f"📂 加载患者病例: {cases_file}")
    
    cases = tester.load_cases(str(cases_file))
    print(f"  ✓ 加载 {len(cases)} 个测试病例\n")
    
    print("📋 病例类型分布:")
    categories = {}
    for case in cases:
        cat = case['category']
        categories[cat] = categories.get(cat, 0) + 1
    for cat, count in categories.items():
        print(f"  - {cat}: {count} 例")
    print()
    
    print("="*70)
    print("开始执行测试")
    print("="*70 + "\n")
    
    results = await tester.run_all_tests(cases)
    
    print("\n" + "="*70)
    print("生成测试报告")
    print("="*70 + "\n")
    
    report = tester.generate_report()
    
    json_path = tester.save_report(report)
    md_path = tester.generate_markdown_report(report)
    
    stats = report['statistics']
    
    print("="*70)
    print("测试结果摘要")
    print("="*70)
    print(f"总测试病例数: {stats['total_cases']}")
    print(f"总体正确数: {stats['overall_correct']}")
    print(f"总体正确率: {stats['overall_accuracy']:.2%}")
    print(f"L1层正确率: {stats['l1_accuracy']:.2%}")
    print(f"L2层正确率: {stats['l2_accuracy']:.2%}")
    print()
    
    print("按病例类型统计:")
    for cat, data in stats['by_category'].items():
        accuracy = data['correct'] / data['total'] if data['total'] > 0 else 0
        print(f"  - {cat}: {data['correct']}/{data['total']} ({accuracy:.2%})")
    
    print()
    print("="*70)
    print(f"测试结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    print()
    print(f"📄 报告已生成:")
    print(f"  - JSON: {json_path}")
    print(f"  - Markdown: {md_path}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
