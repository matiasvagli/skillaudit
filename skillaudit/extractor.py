"""Extrae metadata del package descargado (package.json, README, MCP schema)."""

import json
from pathlib import Path
from typing import Any

from .models import SkillMetadata, SkillTool


def extract_metadata(package_dir: Path) -> SkillMetadata:
    """Lee package.json y README para construir SkillMetadata."""
    pkg_json = _read_package_json(package_dir)
    readme = _read_readme(package_dir)
    tools = _extract_tools(pkg_json, package_dir)
    entrypoint = _find_entrypoint(pkg_json, package_dir)

    return SkillMetadata(
        package_name=pkg_json.get("name", package_dir.name),
        version=pkg_json.get("version", "unknown"),
        short_description=pkg_json.get("description", "Sin descripción"),
        long_description=readme,
        tools=tools,
        entrypoint=entrypoint,
        raw_package_json=pkg_json,
    )


def _read_package_json(package_dir: Path) -> dict[str, Any]:
    pkg_file = package_dir / "package.json"
    if not pkg_file.exists():
        raise FileNotFoundError(f"No se encontró package.json en {package_dir}")
    with pkg_file.open() as f:
        return json.load(f)


def _read_readme(package_dir: Path) -> str:
    for name in ["README.md", "README.txt", "README", "readme.md"]:
        candidate = package_dir / name
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="replace")
    return ""


def _extract_tools(pkg_json: dict[str, Any], package_dir: Path) -> list[SkillTool]:
    """Intenta extraer tools del campo mcp o archivos de schema."""
    # Opción 1: campo "mcp" dentro de package.json
    mcp_config = pkg_json.get("mcp", {})
    if mcp_config.get("tools"):
        return [
            SkillTool(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in mcp_config["tools"]
        ]

    # Opción 2: archivo mcp.json o schema.json en el package
    for schema_file in ["mcp.json", "schema.json", "tools.json"]:
        candidate = package_dir / schema_file
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text())
                tools_raw = data.get("tools", [])
                return [
                    SkillTool(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                    )
                    for t in tools_raw
                ]
            except json.JSONDecodeError:
                pass

    # No se encontraron tools declaradas estáticamente
    return []


def _find_entrypoint(pkg_json: dict[str, Any], package_dir: Path) -> str:
    """Encuentra el entrypoint del MCP server."""
    # MCP servers suelen usar bin o main
    bin_field = pkg_json.get("bin", {})
    if isinstance(bin_field, str):
        return bin_field
    if isinstance(bin_field, dict):
        # Tomar el primer valor del bin map
        for v in bin_field.values():
            return v

    main = pkg_json.get("main", "")
    if main and (package_dir / main).exists():
        return main

    # Fallback: buscar index.js en dist/ o src/
    for candidate in ["dist/index.js", "src/index.js", "index.js", "build/index.js"]:
        if (package_dir / candidate).exists():
            return candidate

    return ""
