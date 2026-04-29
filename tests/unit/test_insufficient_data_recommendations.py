"""测试 L2 初筛分诊：insufficient_data（数据不足）分支。

目标：用 10-20 例明确的“数据不足”病例，验证：
1) 分诊结果进入 uncertain 且 confidence_level=insufficient_data；
2) recommended_tests 是“补检建议”，具备针对性（与缺失字段对应）和可读性（中文、人类可读）；
3) 建议列表去重且保持顺序。

说明：为避免依赖线上 LLM 或外部规则文件，本测试在 tmp_path 中构造最小规则库与字段映射。
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import textwrap
import time
from typing import Any, Dict, List

import pytest


def _write_yaml(path: Path, content: str) -> None:
    normalized = textwrap.dedent(content).strip() + "\n"
    path.write_text(normalized, encoding="utf-8")


def _truthy_env(var_name: str, default: str = "0") -> bool:
    value = str(os.getenv(var_name, default)).strip().lower()
    return value not in {"", "0", "false", "no", "off"}


@pytest.fixture(scope="session")
def record_results() -> List[Dict[str, Any]]:
    """记录每个测试用例的实际输出，便于回溯与人工审阅。

    默认会在会话结束时写入：tests/results/insufficient_data_recommendations.json
    可用环境变量控制：
    - TRIAGE_TEST_RECORD=0  关闭落盘
    """

    records: List[Dict[str, Any]] = []
    yield records

    if not _truthy_env("TRIAGE_TEST_RECORD", default="1"):
        return

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    out_path = results_dir / "insufficient_data_recommendations.json"
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cases": records,
        "case_count": len(records),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture()
def rules_dir(tmp_path: Path) -> Path:
    """构造最小 rules 目录：common/rare + field_test_mapping。"""

    # 常见病规则可以为空（仅保留元信息），保证 load_rules 不报错
    _write_yaml(
        tmp_path / "common_diseases.yaml",
        """
        version: "test"
        last_updated: "2026-04-13"
        """,
    )

    # 罕见病：核心规则 required=true，缺失时应触发 insufficient_data
    # 注意：urgency 统一设为 routine，避免触发 triage 中的 LLM 风险复核分支。
    _write_yaml(
        tmp_path / "rare_diseases.yaml",
        """
        version: "test"
        last_updated: "2026-04-13"

        wilson_like:
          name: "Wilson 类（测试用）"
          category: "rare"
          urgency: "routine"
          core_rules:
            - field: "age"
              operator: "<"
              value: 40
              required: true
            - field: "labs.Ceruloplasmin"
              operator: "<"
              value: 0.20
              required: true
          supporting_rules: []
          thresholds:
            high_confidence: 0.5
            medium_confidence: 0.25
            low_confidence: 0.15

        hemochrom_like:
          name: "血色病类（测试用）"
          category: "rare"
          urgency: "routine"
          core_rules:
            - field: "age"
              operator: ">"
              value: 40
              required: true
            - field: "labs.ferritin"
              operator: ">"
              value: 300
              required: true
            - field: "labs.transferrin_saturation"
              operator: ">"
              value: 45
              required: true
          supporting_rules: []
          thresholds:
            high_confidence: 0.7
            medium_confidence: 0.45
            low_confidence: 0.25

        young_onset:
          name: "青少年起病（测试用）"
          category: "rare"
          urgency: "routine"
          core_rules:
            - field: "age"
              operator: "<"
              value: 18
              required: true
          supporting_rules: []
          thresholds:
            high_confidence: 0.7
            medium_confidence: 0.45
            low_confidence: 0.25
        """,
    )

    # 字段 -> 检查项映射：用于把 field_path 转成可读补检建议
    _write_yaml(
        tmp_path / "field_test_mapping.yaml",
        """
        version: "test"
        last_updated: "2026-04-13"
        mapping:
          age: "年龄/出生年"
          labs.Ceruloplasmin: "血清铜蓝蛋白"
          labs.ferritin: "血清铁蛋白"
          labs.transferrin_saturation: "转铁蛋白饱和度"
        """,
    )

    return tmp_path


def _assert_readable(recommended_tests: List[str]) -> None:
    assert recommended_tests, "recommended_tests 不应为空"
    for item in recommended_tests:
        assert isinstance(item, str) and item.strip(), "补检建议必须是非空字符串"
        # 规则字段路径通常含 '.'；可读建议不应直接暴露 field_path
        assert not item.strip().startswith(("labs.", "history.", "symptoms."))
        assert "." not in item, f"补检建议可读性不足（疑似 field_path 泄漏）：{item}"


@pytest.mark.parametrize(
    "case",
    [
        {
            "id": "数据不足-01-缺age和铜蓝蛋白",
            "patient": {"gender": "male", "labs": {}},
            "expected": ["年龄/出生年", "血清铜蓝蛋白", "血清铁蛋白", "转铁蛋白饱和度"],
        },
        {
            "id": "数据不足-02-仅缺铜蓝蛋白",
            "patient": {"age": 20, "labs": {}},
            "expected": ["血清铜蓝蛋白"],
        },
        {
            "id": "数据不足-03-仅缺铁蛋白",
            "patient": {"age": 50, "labs": {"transferrin_saturation": 60}},
            "expected": ["血清铁蛋白"],
        },
        {
            "id": "数据不足-04-仅缺转铁饱和度",
            "patient": {"age": 50, "labs": {"ferritin": 800}},
            "expected": ["转铁蛋白饱和度"],
        },
        {
            "id": "数据不足-05-缺铁蛋白和转铁饱和度",
            "patient": {"age": 50, "labs": {}},
            "expected": ["血清铁蛋白", "转铁蛋白饱和度"],
        },
        {
            "id": "数据不足-06-缺铜蓝蛋白+铁蛋白",
            "patient": {"age": 25, "labs": {"transferrin_saturation": 70}},
            "expected": ["血清铜蓝蛋白"],
        },
        {
            "id": "数据不足-07-缺全部四项",
            "patient": {"labs": {}},
            "expected": ["年龄/出生年", "血清铜蓝蛋白", "血清铁蛋白", "转铁蛋白饱和度"],
        },
        {
            "id": "数据不足-08-labs大小写混用仍能识别缺失",
            "patient": {"AGE": 30, "LABS": {"Ferritin": 500}},
            "expected": ["血清铜蓝蛋白"],
        },
        {
            "id": "数据不足-09-仅缺age但应去重一次",
            "patient": {"labs": {"ceruloplasmin": 0.12}},
            "expected": ["年龄/出生年", "血清铁蛋白", "转铁蛋白饱和度"],
        },
        {
            "id": "数据不足-10-存在无关字段不影响补检",
            "patient": {"age": 33, "bmi": 30.1, "labs": {"ALT": 88}},
            "expected": ["血清铜蓝蛋白"],
        },
        {
            "id": "数据不足-11-缺转铁饱和度且建议可读",
            "patient": {"age": 41, "labs": {"Ferritin": 1200}},
            "expected": ["转铁蛋白饱和度"],
        },
        {
            "id": "数据不足-12-青少年起病规则缺age",
            "patient": {"labs": {"ferritin": 600, "transferrin_saturation": 80}},
            "expected": ["年龄/出生年", "血清铜蓝蛋白"],
        },
        {
            "id": "数据不足-13-只补铜蓝蛋白（已有age满足）",
            "patient": {"age": 16, "labs": {}},
            "expected": ["血清铜蓝蛋白"],
        },
        {
            "id": "数据不足-14-铁蛋白已给但转铁饱和度缺失",
            "patient": {"age": 60, "labs": {"ferritin": 999}},
            "expected": ["转铁蛋白饱和度"],
        },
        {
            "id": "数据不足-15-转铁饱和度已给但铁蛋白缺失",
            "patient": {"age": 60, "labs": {"transferrin_saturation": 66}},
            "expected": ["血清铁蛋白"],
        },
    ],
    ids=lambda c: c["id"],
)
def test_triage_insufficient_data_cases(
    rules_dir: Path,
    record_results: List[Dict[str, Any]],
    case: Dict[str, Any],
):
    # 延迟导入，避免在收集阶段绑定路径
    import asyncio
    import sys

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from core.triage import IntelligentTriage

    triage = IntelligentTriage(rules_dir=str(rules_dir))
    verbose_flow = _truthy_env("TRIAGE_TEST_VERBOSE", default="0")

    if verbose_flow:
        print(f"\n[CASE] {case['id']}")
        print(f"  patient={case['patient']}")

    record: Dict[str, Any] = {
        "id": case["id"],
        "patient": case["patient"],
        "expected": case["expected"],
        "status": "unknown",
    }

    try:
        result = asyncio.run(triage.triage(case["patient"]))
        record["triage"] = {
            "path": result.path,
            "confidence_level": result.confidence_level,
            "uncertainty_reason": result.uncertainty_reason,
            "recommended_tests": list(result.recommended_tests or []),
            "method": (result.metadata or {}).get("method"),
        }

        if verbose_flow:
            print(f"  path={result.path} confidence_level={result.confidence_level}")
            print(f"  recommended_tests={result.recommended_tests}")

        assert result.path == "uncertain"
        assert result.confidence_level == "insufficient_data"
        assert result.uncertainty_reason and "核心检查缺失" in result.uncertainty_reason

        assert result.recommended_tests == case["expected"]
        _assert_readable(result.recommended_tests)

        record["status"] = "passed"
    except Exception as exc:  # noqa: BLE001
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        record_results.append(record)
