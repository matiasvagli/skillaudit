"""
SkillAudit como MCP Server puramente observacional.

Delega la IA al cliente (Gemini/Claude). 
El servidor solo se encarga de descargar, extraer metadata y correr cosas en Docker.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .downloader import download_package
from .extractor import extract_metadata
from .sandbox_runner import create_sandbox
from .mcp_executor import run_scenarios, _build_driver_script, _discover_entrypoint, _build_jsonrpc_sequence
from .behavior_monitor import capture_behavior
from .models import TestScenario

mcp = FastMCP(
    name="skillaudit",
    instructions=(
        "Eres un analizador de seguridad de MCP servers. "
        "Usa get_package_metadata para investigar qué dice hacer un package, "
        "luego inventa escenarios de prueba y usa run_package_tests para ejecutarlos "
        "en un sandbox. Analiza los resultados del filesystem y red devueltos."
    ),
)


@mcp.tool()
def get_package_metadata(package_name: str) -> str:
    """
    Descarga un package npm y extrae su metadata (README y tools declaradas).
    Usá esto PRIMERO para entender qué dice hacer el package antes de testearlo.
    """
    with tempfile.TemporaryDirectory(prefix="skillaudit-") as tmpdir:
        work_dir = Path(tmpdir)
        try:
            package_dir = download_package(package_name, work_dir)
            metadata = extract_metadata(package_dir)

            return json.dumps(
                {
                    "package": f"{metadata.package_name}@{metadata.version}",
                    "description": metadata.short_description,
                    "readme": metadata.long_description[:2500] + "\n...(truncado)",
                    "declared_tools": [
                        {"name": t.name, "description": t.description, "schema": t.input_schema}
                        for t in metadata.tools
                    ],
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})


@mcp.tool()
def run_package_tests(package_name: str, test_scenarios: list[dict[str, Any]]) -> str:
    """
    Ejecuta test scenarios contra un MCP server en el sandbox y devuelve logs crudos de comportamiento.
    
    Args:
        package_name: Nombre del package npm
        test_scenarios: Lista de tests. Formato: [{"name": "test1", "tool": "read_file", "args": {"path": "/tmp"}}]
    """
    scenarios = [
        TestScenario(
            name=s.get("name", "Test"),
            tool=s.get("tool", ""),
            args=s.get("args", {}),
            description="",
        )
        for s in test_scenarios
        if s.get("tool")
    ]

    with tempfile.TemporaryDirectory(prefix="skillaudit-") as tmpdir:
        work_dir = Path(tmpdir)
        try:
            package_dir = download_package(package_name, work_dir)
            metadata = extract_metadata(package_dir)

            with create_sandbox(package_dir) as sandbox:
                entrypoint = metadata.entrypoint or _discover_entrypoint(sandbox)
                messages = _build_jsonrpc_sequence(scenarios)
                driver_script = _build_driver_script(entrypoint, messages)

                # Monitorear
                try:
                    behavior = capture_behavior(sandbox, entrypoint, driver_script)
                except Exception as e:
                    from .models import BehaviorReport
                    behavior = BehaviorReport(raw_stderr=f"Error strace: {e}")

                # Respuestas
                call_results, stdout, stderr = run_scenarios(sandbox, entrypoint, scenarios)

                file_ev = [f"{e.operation.upper()}: {e.path}" for e in behavior.file_events]
                net_ev = [f"{e.address}:{e.port}" for e in behavior.network_events]
                proc_ev = [e.command for e in behavior.process_events]

                return json.dumps(
                    {
                        "mcp_responses": [
                            {
                                "scenario": r.scenario.name,
                                "success": r.success,
                                "response": r.response,
                                "error": r.error,
                            }
                            for r in call_results
                        ],
                        "behavior_logs": {
                            "filesystem_activity": file_ev[:100],  # cap
                            "network_activity": net_ev,
                            "subprocesses_spawned": proc_ev,
                            "honeypot_accesses": behavior.honeypot_accesses,
                        },
                        "stderr": stderr[-1000:] if stderr else "",
                    },
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception as e:
            return json.dumps({"error": str(e)})


@mcp.tool()
def check_docker_status() -> str:
    """Verifica si Docker y la imagen del sandbox están listos."""
    import docker as docker_sdk
    try:
        client = docker_sdk.from_env()
        client.ping()
        client.images.get("skillaudit-sandbox:latest")
        return "✅ Docker OK. Sandbox image OK."
    except Exception as e:
        return f"❌ Error: {e}"


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
