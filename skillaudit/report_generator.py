"""Genera reportes de seguridad en formato JSON y Markdown."""

import json
from datetime import datetime
from pathlib import Path

from .models import BehaviorReport, SecurityAnalysis, SkillMetadata, TestScenario
from .mcp_executor import MCPCallResult

SEVERITY_ICONS = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "info": "ℹ️",
}

RISK_COLORS = {
    "safe": "✅ SAFE",
    "low": "🟢 LOW",
    "medium": "🟡 MEDIUM",
    "high": "🔴 HIGH",
    "critical": "💀 CRITICAL",
}

RECOMMENDATION_ICONS = {
    "SAFE TO INSTALL": "✅",
    "REVIEW MANUALLY": "⚠️",
    "DO NOT INSTALL": "❌",
}


def generate_report(
    metadata: SkillMetadata,
    scenarios: list[TestScenario],
    call_results: list[MCPCallResult],
    behavior: BehaviorReport,
    analysis: SecurityAnalysis,
    output_dir: Path,
) -> tuple[Path, Path]:
    """
    Genera el reporte en JSON y Markdown.
    Retorna (json_path, md_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Nombre base del archivo
    safe_name = metadata.package_name.replace("/", "-").replace("@", "").strip("-")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = f"{safe_name}-{timestamp}"

    # JSON — datos completos
    json_data = _build_json(metadata, scenarios, call_results, behavior, analysis)
    json_path = output_dir / f"{base_name}.json"
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False))

    # Markdown — reporte legible
    md_content = _build_markdown(metadata, scenarios, call_results, behavior, analysis)
    md_path = output_dir / f"{base_name}.md"
    md_path.write_text(md_content, encoding="utf-8")

    return json_path, md_path


def _build_json(
    metadata: SkillMetadata,
    scenarios: list[TestScenario],
    call_results: list[MCPCallResult],
    behavior: BehaviorReport,
    analysis: SecurityAnalysis,
) -> dict:
    return {
        "skillaudit_version": "0.1.0",
        "generated_at": datetime.now().isoformat(),
        "package": {
            "name": metadata.package_name,
            "version": metadata.version,
            "description": metadata.short_description,
            "tools": [
                {"name": t.name, "description": t.description}
                for t in metadata.tools
            ],
        },
        "test_scenarios": [
            {
                "name": s.name,
                "tool": s.tool,
                "args": s.args,
                "description": s.description,
            }
            for s in scenarios
        ],
        "scenario_results": [
            {
                "scenario": r.scenario.name,
                "tool": r.scenario.tool,
                "success": r.success,
                "error": r.error,
                "response": r.response,
            }
            for r in call_results
        ],
        "behavior": {
            "file_events": [
                {"path": e.path, "operation": e.operation}
                for e in behavior.file_events
            ],
            "network_events": [
                {"address": e.address, "port": e.port}
                for e in behavior.network_events
            ],
            "process_events": [
                {"command": e.command} for e in behavior.process_events
            ],
            "honeypot_accesses": behavior.honeypot_accesses,
        },
        "security_analysis": {
            "risk_score": analysis.risk_score,
            "risk_level": analysis.risk_level,
            "recommendation": analysis.recommendation,
            "reasoning": analysis.raw_analysis,
            "findings": [
                {
                    "severity": f.severity,
                    "type": f.type,
                    "description": f.description,
                }
                for f in analysis.findings
            ],
            "expected_behavior": analysis.expected_behavior,
        },
    }


def _build_markdown(
    metadata: SkillMetadata,
    scenarios: list[TestScenario],
    call_results: list[MCPCallResult],
    behavior: BehaviorReport,
    analysis: SecurityAnalysis,
) -> str:
    risk_display = RISK_COLORS.get(analysis.risk_level, analysis.risk_level.upper())
    rec_icon = RECOMMENDATION_ICONS.get(analysis.recommendation, "⚠️")
    lines = [
        f"# 🔍 SkillAudit Report: `{metadata.package_name}`",
        "",
        f"**Version:** {metadata.version}  ",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Risk Level:** {risk_display} ({analysis.risk_score}/100)  ",
        f"**Recommendation:** {rec_icon} {analysis.recommendation}",
        "",
        "---",
        "",
        "## 📋 Package Description",
        "",
        f"> {metadata.short_description}",
        "",
    ]

    # Tools declaradas
    if metadata.tools:
        lines += ["**Declared Tools:**", ""]
        for t in metadata.tools:
            lines.append(f"- `{t.name}`: {t.description}")
        lines.append("")

    # Test scenarios y resultados
    lines += [
        "---",
        "",
        "## 🏃 Test Execution",
        "",
        f"Ran **{len(scenarios)} test scenarios**:",
        "",
    ]
    for r in call_results:
        icon = "✅" if r.success else ("⚠️" if r.error else "❓")
        lines.append(f"- {icon} **{r.scenario.name}** (`{r.scenario.tool}`)")
        if r.error:
            lines.append(f"  - Error: {r.error}")
    lines.append("")

    # Behavior summary
    lines += [
        "---",
        "",
        "## 🔬 Behavior Observed",
        "",
        f"- **File system accesses:** {len(behavior.file_events)}",
        f"- **Network connection attempts:** {len(behavior.network_events)}",
        f"- **Subprocesses spawned:** {len(behavior.process_events)}",
        f"- **Honeypot files accessed:** {len(behavior.honeypot_accesses)}",
        "",
    ]

    if behavior.honeypot_accesses:
        lines += ["> 🚨 **HONEYPOT TRIGGERED:**", ""]
        for hp in behavior.honeypot_accesses:
            lines.append(f"> - `{hp}` was accessed")
        lines.append("")

    if behavior.network_events:
        lines += ["**Network connections attempted:**", ""]
        for ne in behavior.network_events:
            lines.append(f"- `{ne.address}:{ne.port}`")
        lines.append("")

    # Security findings
    lines += [
        "---",
        "",
        "## 🛡️ Security Analysis",
        "",
        f"**Risk Score: {analysis.risk_score}/100**",
        "",
    ]

    if analysis.findings:
        # Agrupar por severity
        for sev in ["critical", "high", "medium", "low", "info"]:
            sev_findings = [f for f in analysis.findings if f.severity == sev]
            if sev_findings:
                icon = SEVERITY_ICONS.get(sev, "•")
                lines.append(f"### {icon} {sev.capitalize()} Issues")
                lines.append("")
                for f in sev_findings:
                    lines.append(f"- **{f.type.replace('_', ' ').title()}**: {f.description}")
                lines.append("")
    else:
        lines += ["✅ No security issues found.", ""]

    if analysis.expected_behavior:
        lines += ["### ✅ Expected Behavior Confirmed", ""]
        for eb in analysis.expected_behavior:
            lines.append(f"- {eb}")
        lines.append("")

    if analysis.raw_analysis:
        lines += ["### 💬 Analyst Notes", "", analysis.raw_analysis, ""]

    lines += [
        "---",
        "",
        f"## {rec_icon} Recommendation: {analysis.recommendation}",
        "",
        "_Report generated by [SkillAudit](https://github.com/skillaudit/skillaudit)_",
    ]

    return "\n".join(lines)
