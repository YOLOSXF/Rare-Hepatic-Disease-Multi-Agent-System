"""
LangGraph整体框架流程测试
使用外部患者数据测试完整的五层对抗推理流程
"""

import sys
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.graph_orchestrator import LangGraphDiagnosticGraph
from core.state_definition import DiagnosticState
from loguru import logger


@dataclass
class TestResult:
    """测试结果"""
    case_id: str
    case_name: str
    category: str
    
    expected: Dict[str, Any]
    actual: Dict[str, Any]
    
    passed: bool = False
    failure_reason: str = ""
    execution_time_ms: int = 0
    error: str = ""


class LangGraphFlowTester:
    """LangGraph整体流程测试器"""
    
    def __init__(self, results_dir: str = "tests/results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        self.graph = LangGraphDiagnosticGraph()
        self.test_results: List[TestResult] = []
    
    def load_patient_cases(self, json_file: str) -> List[Dict]:
        """从JSON文件加载患者病例"""
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('test_cases', [])
    
    async def execute_full_pipeline(self, patient_data: Dict, case_id: str) -> Dict[str, Any]:
        """执行完整的五层对抗推理流程"""
        try:
            result = await self.graph.run_full_pipeline(
                patient_data=patient_data,
                config={'thread_id': case_id}
            )
            return {
                "success": True,
                "report": result
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "report": None
            }
    
    def compare_results(
        self,
        actual: Dict[str, Any],
        expected: Dict[str, Any]
    ) -> tuple[bool, str]:
        """比较测试结果与预期结果"""
        reasons = []
        passed = True
        
        if not actual.get("success"):
            return False, f"执行失败: {actual.get('error', '未知错误')}"
        
        report = actual.get("report", {})
        if not report:
            return False, "报告为空"
        
        expected_L1 = expected.get("L1", {})
        expected_L2 = expected.get("L2", {})
        
        # L1: 检查数据完整性评分
        expected_trigger = expected_L1.get("should_trigger_incomplete", None)
        if expected_trigger is not None:
            completeness_score = report.get('data_completeness_score', 0)
            actual_trigger = completeness_score < 0.7
            if expected_trigger != actual_trigger:
                passed = False
                reasons.append(
                    f"信息不全触发状态不匹配: 预期{expected_trigger}, 实际{actual_trigger}"
                )
        
        expected_score_range = expected_L1.get("expected_completeness_score", None)
        if expected_score_range:
            actual_score = report.get('data_completeness_score', 0)
            if expected_score_range.startswith(">="):
                threshold = float(expected_score_range.replace(">=", ""))
                if actual_score < threshold:
                    passed = False
                    reasons.append(
                        f"完整度评分不达标: 预期{expected_score_range}, 实际{actual_score:.2f}"
                    )
            elif expected_score_range.startswith("<"):
                threshold = float(expected_score_range.replace("<", ""))
                if actual_score >= threshold:
                    passed = False
                    reasons.append(
                        f"完整度评分过高: 预期{expected_score_range}, 实际{actual_score:.2f}"
                    )
        
        # L2: 检查分诊路径
        expected_path = expected_L2.get("expected_path", None)
        if expected_path:
            triage_result = report.get('triage', {})
            actual_path = triage_result.get('path', '') if triage_result else ''
            if expected_path not in str(actual_path):
                passed = False
                reasons.append(
                    f"分诊路径不匹配: 预期包含'{expected_path}', 实际'{actual_path}'"
                )
        
        # L2: 检查诊断关键词
        expected_keywords = expected_L2.get("expected_diagnosis_contains", [])
        if expected_keywords:
            diagnosis_obj = report.get('diagnosis', {})
            actual_diagnosis = ''
            if isinstance(diagnosis_obj, dict):
                actual_diagnosis = diagnosis_obj.get('disease', '')
            elif isinstance(diagnosis_obj, str):
                actual_diagnosis = diagnosis_obj
            
            if actual_diagnosis:
                keyword_found = any(kw.lower() in actual_diagnosis.lower() for kw in expected_keywords)
                if not keyword_found:
                    passed = False
                    reasons.append(
                        f"诊断关键词不匹配: 预期包含{expected_keywords}, 实际'{actual_diagnosis}'"
                    )
        
        # L2: 检查罕见病预警
        expected_rare = expected_L2.get("expected_is_rare_alert", None)
        if expected_rare is not None:
            triage_result = report.get('triage', {})
            actual_rare = triage_result.get('is_rare_disease_alert', False) if triage_result else False
            if expected_rare != actual_rare:
                passed = False
                reasons.append(
                    f"罕见病预警状态不匹配: 预期{expected_rare}, 实际{actual_rare}"
                )
        
        # L2: 检查置信度级别
        expected_conf_levels = expected_L2.get("expected_confidence_level", [])
        if expected_conf_levels:
            triage_result = report.get('triage', {})
            actual_conf = triage_result.get('confidence_level', '') if triage_result else ''
            if actual_conf not in expected_conf_levels:
                passed = False
                reasons.append(
                    f"置信度级别不匹配: 预期{expected_conf_levels}, 实际'{actual_conf}'"
                )
        
        failure_reason = "; ".join(reasons) if reasons else ""
        return passed, failure_reason
    
    async def run_single_case(self, case: Dict) -> TestResult:
        """运行单个测试用例"""
        import time
        start_time = time.time()
        
        case_id = case["case_id"]
        case_name = case["case_name"]
        category = case["category"]
        patient_data = case["patient_data"]
        expected_results = case["expected_results"]
        
        actual = await self.execute_full_pipeline(patient_data, case_id)
        logger.info(f"case_id: {case_id}")
        logger.info(f"expected_results: {expected_results}")
        logger.info(f"actual: {actual}")
        
        passed, failure_reason = self.compare_results(actual, expected_results)
        
        report = actual.get("report", {})
        triage_result = report.get('triage', {}) if report else {}
        diagnosis_obj = report.get('diagnosis', {}) if report else {}
        
        actual_diagnosis = ''
        if isinstance(diagnosis_obj, dict):
            actual_diagnosis = diagnosis_obj.get('disease', '')
        elif isinstance(diagnosis_obj, str):
            actual_diagnosis = diagnosis_obj
        
        result = TestResult(
            case_id=case_id,
            case_name=case_name,
            category=category,
            expected=expected_results,
            actual={
                "success": actual.get("success"),
                "report_summary": {
                    "data_completeness_score": report.get('data_completeness_score') if report else None,
                    "path": triage_result.get('path') if triage_result else None,
                    "diagnosis": actual_diagnosis,
                    "confidence_level": triage_result.get('confidence_level') if triage_result else None,
                    "is_rare_disease_alert": triage_result.get('is_rare_disease_alert') if triage_result else None
                } if report else None
            },
            passed=passed,
            failure_reason=failure_reason,
            execution_time_ms=int((time.time() - start_time) * 1000),
            error=actual.get("error", "") if not actual.get("success") else ""
        )
        
        return result
    
    async def run_all_cases(self, cases: List[Dict]):
        """运行所有测试用例"""
        for i, case in enumerate(cases, 1):
            print(f"  [{i}/{len(cases)}] {case['case_id']}: {case['case_name']}")
            result = await self.run_single_case(case)
            self.test_results.append(result)
            
            status = "✅" if result.passed else "❌"
            print(f"      {status} {result.execution_time_ms}ms")
            if result.failure_reason:
                print(f"      失败原因: {result.failure_reason}")
    
    def generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r.passed)
        
        category_stats = {}
        for result in self.test_results:
            cat = result.category
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "passed": 0}
            category_stats[cat]["total"] += 1
            if result.passed:
                category_stats[cat]["passed"] += 1
        
        failed_results = []
        for result in self.test_results:
            if not result.passed:
                failed_results.append({
                    "case_id": result.case_id,
                    "case_name": result.case_name,
                    "category": result.category,
                    "expected": result.expected,
                    "actual": result.actual,
                    "failure_reason": result.failure_reason,
                    "error": result.error
                })
        
        return {
            "report_id": f"RPT-LANGGRAPH-FULL-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_cases": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": f"{passed/total*100:.1f}%" if total > 0 else "0%"
            },
            "category_statistics": category_stats,
            "failed_cases": failed_results
        }
    
    def save_report(self, report: Dict, filename: Optional[str] = None) -> str:
        """保存JSON报告"""
        if filename is None:
            filename = f"langgraph_full_flow_test_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        
        filepath = self.results_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        return str(filepath)
    
    def generate_markdown_report(self, report: Dict) -> str:
        """生成Markdown报告"""
        summary = report["summary"]
        
        lines = [
            "# LangGraph整体框架流程测试报告",
            "",
            f"**报告ID**: {report['report_id']}",
            f"**生成时间**: {report['generated_at']}",
            "",
            "## 测试摘要",
            "",
            "| 指标 | 值 |",
            "|------|-----|",
            f"| 总测试数 | {summary['total_cases']} |",
            f"| 通过数 | {summary['passed']} |",
            f"| 失败数 | {summary['failed']} |",
            f"| **总体通过率** | **{summary['pass_rate']}** |",
            "",
            "## 按类别统计",
            "",
            "| 类别 | 总数 | 通过 | 通过率 |",
            "|------|------|------|--------|",
        ]
        
        for cat, stats in report["category_statistics"].items():
            rate = f"{stats['passed']/stats['total']*100:.1f}%" if stats['total'] > 0 else "0%"
            lines.append(
                f"| {cat} | {stats['total']} | {stats['passed']} | {rate} |"
            )
        
        if report["failed_cases"]:
            lines.extend([
                "",
                "## 失败用例分析",
                "",
            ])
            
            for case in report["failed_cases"]:
                lines.extend([
                    f"### {case['case_id']}: {case['case_name']}",
                    "",
                    f"**类别**: {case['category']}",
                    "",
                    f"**失败原因**: {case['failure_reason']}",
                    "",
                ])
                
                if case.get("error"):
                    lines.extend([
                        f"**错误信息**: {case['error']}",
                        "",
                    ])
                
                lines.extend([
                    "**预期结果**:",
                    f"```json",
                    json.dumps(case['expected'], ensure_ascii=False, indent=2),
                    f"```",
                    "",
                    "**实际结果**:",
                    f"```json",
                    json.dumps(case['actual'], ensure_ascii=False, indent=2),
                    f"```",
                    "",
                ])
        
        content = "\n".join(lines)
        
        filename = f"langgraph_full_flow_test_{datetime.now().strftime('%Y%m%d%H%M%S')}.md"
        filepath = self.results_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return str(filepath)


async def main():
    """主测试函数"""
    print("\n" + "="*70)
    print("LangGraph整体框架流程测试")
    print("="*70)
    print(f"测试开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")
    
    tester = LangGraphFlowTester(results_dir="tests/results")
    
    cases_file = Path(__file__).parent / "patient_cases_suite.json"
    print(f"📂 加载患者病例数据: {cases_file}")
    
    cases = tester.load_patient_cases(str(cases_file))
    print(f"  ✓ 加载 {len(cases)} 个测试用例\n")
    
    print("📋 执行测试用例")
    print("-"*70)
    
    await tester.run_all_cases(cases)
    
    print("\n" + "="*70)
    print("生成测试报告")
    print("="*70 + "\n")
    
    report = tester.generate_report()
    
    json_path = tester.save_report(report)
    md_path = tester.generate_markdown_report(report)
    
    summary = report["summary"]
    
    print("="*70)
    print("测试结果摘要")
    print("="*70)
    print(f"总测试数: {summary['total_cases']}")
    print(f"通过数: {summary['passed']}")
    print(f"失败数: {summary['failed']}")
    print(f"总体通过率: {summary['pass_rate']}")
    print()
    
    print("按类别统计:")
    for cat, stats in report["category_statistics"].items():
        rate = stats["passed"] / stats["total"] * 100 if stats["total"] > 0 else 0
        print(f"  - {cat}: {stats['passed']}/{stats['total']} ({rate:.1f}%)")
    
    if report["failed_cases"]:
        print()
        print("="*70)
        print("失败用例汇总")
        print("="*70)
        for case in report["failed_cases"]:
            print(f"\n{case['case_id']}: {case['case_name']}")
            print(f"  失败原因: {case['failure_reason']}")
            if case.get("error"):
                print(f"  错误信息: {case['error']}")
    
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
