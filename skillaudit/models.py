"""Modelos de datos compartidos entre módulos."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillTool:
    """Representa una tool declarada por el MCP server."""
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillMetadata:
    """Metadatos extraídos del package npm."""
    package_name: str
    version: str
    short_description: str
    long_description: str  # README completo
    tools: list[SkillTool] = field(default_factory=list)
    entrypoint: str = ""  # Ej: "dist/index.js"
    raw_package_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestScenario:
    """Un caso de prueba generado para una tool."""
    name: str
    tool: str
    args: dict[str, Any]
    description: str = ""


@dataclass
class NetworkEvent:
    address: str
    port: int
    bytes_sent: int = 0


@dataclass
class FileEvent:
    path: str
    operation: str  # "open", "read", "write", "unlink"


@dataclass
class ProcessEvent:
    command: str


@dataclass
class BehaviorReport:
    """Reporte de comportamiento capturado durante la ejecución."""
    file_events: list[FileEvent] = field(default_factory=list)
    network_events: list[NetworkEvent] = field(default_factory=list)
    process_events: list[ProcessEvent] = field(default_factory=list)
    honeypot_accesses: list[str] = field(default_factory=list)  # paths de honeypots tocados
    raw_strace: str = ""
    raw_stdout: str = ""
    raw_stderr: str = ""


@dataclass
class SecurityFinding:
    severity: str  # "critical", "high", "medium", "low", "info"
    type: str
    description: str


@dataclass
class SecurityAnalysis:
    """Resultado del análisis de seguridad."""
    risk_score: int  # 0-100
    risk_level: str  # "critical", "high", "medium", "low", "safe"
    findings: list[SecurityFinding] = field(default_factory=list)
    expected_behavior: list[str] = field(default_factory=list)
    recommendation: str = ""
    raw_analysis: str = ""
