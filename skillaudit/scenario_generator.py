"""IA #1 — Genera test scenarios basados en la metadata de la skill."""

import json
import re

from .ai_client import ask_ai
from .models import SkillMetadata, SkillTool, TestScenario

_SYSTEM_PROMPT = """\
Eres un experto en seguridad de software especializado en auditar MCP (Model Context Protocol) servers.
Tu tarea es generar casos de prueba para observar el comportamiento real de un MCP server.
Siempre responde ÚNICAMENTE con JSON válido, sin texto adicional, sin markdown, sin explicaciones.
"""


def generate_scenarios(metadata: SkillMetadata) -> list[TestScenario]:
    """
    Usa IA para generar test scenarios basados en la descripción y tools de la skill.
    Retorna entre 4 y 8 TestScenario.
    """
    tools_info = _format_tools(metadata.tools)
    prompt = f"""{_SYSTEM_PROMPT}

El MCP server se llama: {metadata.package_name}
Descripción corta: {metadata.short_description}

README (primeras 1500 chars):
{metadata.long_description[:1500]}

Tools declaradas por el servidor:
{tools_info}

Genera entre 5 y 8 test scenarios JSON-RPC para auditar este MCP server.
Incluye:
1. Escenarios de uso legítimo (según lo que dice que hace)
2. Edge cases (inputs vacíos, paths inválidos, etc.)
3. Escenarios que revelarían comportamiento malicioso si lo hubiera
   (por ejemplo: intentar leer archivos fuera del scope declarado)

IMPORTANTE: los args deben ser realistas para el tool que los recibe.
Si el tool no fue declarado pero lo inferís del README, lo podés incluir.

Responde ÚNICAMENTE con este JSON (sin markdown):
{{
  "scenarios": [
    {{
      "name": "Nombre descriptivo del escenario",
      "tool": "nombre_del_tool",
      "args": {{"param": "valor"}},
      "description": "Por qué este test es relevante para la seguridad"
    }}
  ]
}}
"""

    raw = ask_ai(prompt)
    return _parse_scenarios(raw)


def _format_tools(tools: list[SkillTool]) -> str:
    if not tools:
        return "(No se encontraron tools declaradas estáticamente — se infieren del README)"
    lines = []
    for t in tools:
        lines.append(f"- {t.name}: {t.description}")
        if t.input_schema:
            lines.append(f"  Schema: {json.dumps(t.input_schema, indent=2)[:300]}")
    return "\n".join(lines)


def _parse_scenarios(raw: str) -> list[TestScenario]:
    """Parsea la respuesta JSON del LLM, tolerante a errores."""
    # Limpiar posibles bloques markdown ```json ... ```
    clean = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

    try:
        data = json.loads(clean)
        raw_scenarios = data.get("scenarios", [])
    except json.JSONDecodeError:
        # Intentar extraer el bloque JSON con regex
        match = re.search(r'\{.*\}', clean, re.DOTALL)
        if match:
            data = json.loads(match.group())
            raw_scenarios = data.get("scenarios", [])
        else:
            # Fallback: devolver un escenario genérico
            return [
                TestScenario(
                    name="Llamada básica",
                    tool="ping",
                    args={},
                    description="Escenario de fallback cuando no se pudo parsear la respuesta de IA",
                )
            ]

    return [
        TestScenario(
            name=s.get("name", f"Scenario {i+1}"),
            tool=s.get("tool", ""),
            args=s.get("args", {}),
            description=s.get("description", ""),
        )
        for i, s in enumerate(raw_scenarios)
        if s.get("tool")
    ]
