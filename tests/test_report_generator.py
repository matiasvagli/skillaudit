"""Tests para el módulo report_generator."""

import json
from pathlib import Path

import pytest
from skillaudit.models import (
    BehaviorReport,
    FileEvent,
    NetworkEvent,
    SecurityAnalysis,
    SecurityFinding,
    SkillMetadata,
    SkillTool,
    TestScenario,
)
from skillaudit.mcp_executor import MCPCallResult
from skillaudit.report_generator import generate_report


@pytest.fixture
def sample_metadata():
    return SkillMetadata(
        package_name="@test/csv-parser",
        version="1.0.0",
        short_description="Parses CSV files",
        long_description="# CSV Parser",
        tools=[SkillTool("parse_csv", "Parse a CSV file")],
        entrypoint="index.js",
    )


@pytest.fixture
def sample_behavior():
    return BehaviorReport(
        file_events=[
            FileEvent("/app/index.js", "read"),
            FileEvent("/root/.aws/credentials", "read"),
        ],
        network_events=[NetworkEvent("45.33.22.11", 443)],
        process_events=[],
        honeypot_accesses=["/root/.aws/credentials"],
        raw_strace="execve('/usr/bin/node') = 0\n",
    )


@pytest.fixture
def sample_analysis():
    return SecurityAnalysis(
        risk_score=90,
        risk_level="critical",
        findings=[
            SecurityFinding("critical", "honeypot_access", "Leyó /root/.aws/credentials"),
            SecurityFinding("high", "network_exfiltration", "Intentó conectar a 45.33.22.11:443"),
        ],
        expected_behavior=["Leer archivos CSV"],
        recommendation="DO NOT INSTALL",
        raw_analysis="Comportamiento altamente sospechoso.",
    )


def test_generate_report_creates_files(
    tmp_path, sample_metadata, sample_behavior, sample_analysis
):
    scenario = TestScenario("Parse CSV", "parse_csv", {"path": "/test.csv"})
    result = MCPCallResult(scenario, response=None, error="timeout")

    json_path, md_path = generate_report(
        sample_metadata, [scenario], [result],
        sample_behavior, sample_analysis, tmp_path
    )

    assert json_path.exists()
    assert md_path.exists()


def test_json_report_structure(
    tmp_path, sample_metadata, sample_behavior, sample_analysis
):
    scenario = TestScenario("Parse CSV", "parse_csv", {"path": "/test.csv"})
    result = MCPCallResult(scenario, response=None, error="")

    json_path, _ = generate_report(
        sample_metadata, [scenario], [result],
        sample_behavior, sample_analysis, tmp_path
    )

    data = json.loads(json_path.read_text())
    assert data["package"]["name"] == "@test/csv-parser"
    assert data["security_analysis"]["risk_score"] == 90
    assert data["security_analysis"]["recommendation"] == "DO NOT INSTALL"
    assert len(data["security_analysis"]["findings"]) == 2
    assert data["behavior"]["honeypot_accesses"] == ["/root/.aws/credentials"]


def test_markdown_report_contains_key_sections(
    tmp_path, sample_metadata, sample_behavior, sample_analysis
):
    scenario = TestScenario("Parse CSV", "parse_csv", {"path": "/test.csv"})
    result = MCPCallResult(scenario, response=None, error="")

    _, md_path = generate_report(
        sample_metadata, [scenario], [result],
        sample_behavior, sample_analysis, tmp_path
    )

    content = md_path.read_text()
    assert "SkillAudit Report" in content
    assert "DO NOT INSTALL" in content
    assert "honeypot" in content.lower()
    assert "90/100" in content
