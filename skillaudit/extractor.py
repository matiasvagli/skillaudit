"""Extrae metadata del package descargado (package.json, README, MCP schema)."""

import json
from pathlib import Path
from typing import Any

from .models import SkillMetadata, SkillTool


def extract_metadata(package_dir: Path) -> SkillMetadata:
    """Lee package.json y README para construir SkillMetadata."""
    pkg_json = _read_package_json(package_dir) or _read_pyproject(package_dir) or _read_dist_info(package_dir) or {}
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


def _read_package_json(package_dir: Path) -> dict[str, Any] | None:
    pkg_file = package_dir / "package.json"
    if not pkg_file.exists():
        return None
    with pkg_file.open() as f:
        return json.load(f)


def _read_pyproject(package_dir: Path) -> dict[str, Any] | None:
    """Lee pyproject.toml si existe."""
    try:
        import tomllib as toml # Python 3.11+
    except ImportError:
        try:
            import toml
        except ImportError:
            return None
            
    pyproject_file = package_dir / "pyproject.toml"
    if not pyproject_file.exists():
        return None
        
    with pyproject_file.open("rb") as f:
        data = toml.load(f)
        project = data.get("project", {})
        return {
            "name": project.get("name", ""),
            "version": project.get("version", ""),
            "description": project.get("description", ""),
            "main": _find_python_entrypoint(data, package_dir)
        }


def _read_dist_info(package_dir: Path) -> dict[str, Any] | None:
    """Busca y lee el directorio .dist-info (común en wheels)."""
    dist_info_dirs = list(package_dir.glob("*.dist-info"))
    if not dist_info_dirs:
        return None
        
    dist_info = dist_info_dirs[0]
    metadata_file = dist_info / "METADATA"
    ep_file = dist_info / "entry_points.txt"
    
    data = {"name": "", "version": "", "description": "", "main": ""}
    
    if metadata_file.exists():
        content = metadata_file.read_text(errors="replace")
        for line in content.split("\n"):
            if line.startswith("Name:"):
                data["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Version:"):
                data["version"] = line.split(":", 1)[1].strip()
            elif line.startswith("Summary:"):
                data["description"] = line.split(":", 1)[1].strip()
                
    if ep_file.exists():
        content = ep_file.read_text(errors="replace")
        # Buscar algo como mcp-server-xxx = module:main
        import re
        m = re.search(r'[^=]+=\s*([^:]+):', content)
        if m:
            data["main"] = f"python3 -m {m.group(1).strip()}"
            
    return data


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
    if main:
        # Si parece ser un comando (tiene espacios o empieza por python), no verificamos archivo
        if " " in main or main.startswith("python"):
            return main
        if (package_dir / main).exists():
            return main

    # Fallback Python: buscar __main__.py recursivamente
    for candidate in package_dir.rglob("__main__.py"):
        if "node_modules" not in str(candidate):
            return str(candidate.relative_to(package_dir))

    # Fallback: buscar archivos comunes en la raíz
    for name in ["index.js", "main.py"]:
        if (package_dir / name).exists():
            return name

    return ""


def _find_python_entrypoint(pyproject_data: dict, package_dir: Path) -> str:
    """Busca scripts o entrypoints en la data de pyproject.toml."""
    # Buscar scripts de MCP
    scripts = pyproject_data.get("project", {}).get("scripts", {})
    for name, path in scripts.items():
        if "mcp" in name:
            return f"python3 -m {path.split(':')[0]}"
    return ""
