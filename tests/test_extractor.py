"""Tests para el módulo extractor de metadata."""

import json
import pytest
from pathlib import Path

from skillaudit.extractor import extract_metadata
from skillaudit.models import SkillMetadata


@pytest.fixture
def fake_package(tmp_path: Path) -> Path:
    """Crea un package npm falso para testing."""
    pkg = {
        "name": "@test/csv-parser",
        "version": "1.0.0",
        "description": "MCP server for parsing CSV files",
        "main": "index.js",
        "bin": {"csv-parser": "index.js"},
        "mcp": {
            "tools": [
                {
                    "name": "parse_csv",
                    "description": "Parse a CSV file and return structured data",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                }
            ]
        },
    }
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    (tmp_path / "README.md").write_text("# CSV Parser\n\nParses CSV files via MCP.")
    (tmp_path / "index.js").write_text("console.log('hello')")
    return tmp_path


def test_extract_basic_metadata(fake_package: Path):
    meta = extract_metadata(fake_package)
    assert meta.package_name == "@test/csv-parser"
    assert meta.version == "1.0.0"
    assert "CSV" in meta.short_description


def test_extract_tools(fake_package: Path):
    meta = extract_metadata(fake_package)
    assert len(meta.tools) == 1
    assert meta.tools[0].name == "parse_csv"
    assert "CSV" in meta.tools[0].description


def test_extract_readme(fake_package: Path):
    meta = extract_metadata(fake_package)
    assert "CSV Parser" in meta.long_description


def test_extract_entrypoint(fake_package: Path):
    meta = extract_metadata(fake_package)
    assert meta.entrypoint == "index.js"


def test_missing_readme(fake_package: Path):
    (fake_package / "README.md").unlink()
    meta = extract_metadata(fake_package)
    assert meta.long_description == ""


def test_no_mcp_tools(tmp_path: Path):
    """Sin campo mcp en package.json, tools debe ser lista vacía."""
    pkg = {
        "name": "plain-package",
        "version": "0.1.0",
        "description": "A plain package",
        "main": "index.js",
    }
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    (tmp_path / "index.js").touch()
    meta = extract_metadata(tmp_path)
    assert meta.tools == []
