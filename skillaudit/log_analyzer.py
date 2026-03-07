"""IA #2 — Analiza los logs de comportamiento vs la descripción declarada de la skill."""

import json
import re

from .ai_client import ask_ai
from .models import (
    BehaviorReport,
    SecurityAnalysis,
    SecurityFinding,
    SkillMetadata,
)

_SYSTEM_PROMPT = """\
Eres un experto en seguridad especializado en detectar comportamientos maliciosos en software.
Analiza el comportamiento observado de un MCP server y determina si es consistente con lo que dice hacer.
Siempre responde ÚNICAMENTE con JSON válido, sin texto adicional, sin markdown.
"""


def analyze_behavior(metadata: SkillMetadata, behavior: BehaviorReport) -> SecurityAnalysis:
    """
    IA #2: Compara la descripción declarada con el comportamiento real.
    Retorna SecurityAnalysis con risk_score, findings y recommendation.
    """
    prompt = _build_prompt(metadata, behavior)
    raw = ask_ai(prompt)
    return _parse_analysis(raw)


def _build_prompt(metadata: SkillMetadata, behavior: BehaviorReport) -> str:
    file_events_str = _format_file_events(behavior)
    network_events_str = _format_network_events(behavior)
    process_events_str = _format_process_events(behavior)
    honeypot_str = _format_honeypots(behavior)

    return f"""{_SYSTEM_PROMPT}

=== DESCRIPCIÓN DECLARADA DEL MCP SERVER ===
Nombre: {metadata.package_name}@{metadata.version}
Descripción: {metadata.short_description}

README (primeras 2000 chars):
{metadata.long_description[:2000]}

Tools declaradas: {', '.join(t.name for t in metadata.tools) or '(ninguna declarada)'}

=== COMPORTAMIENTO REAL OBSERVADO ===

📁 Accesos a filesystem:
{file_events_str}

🌐 Intentos de conexión de red:
{network_events_str}

⚙️ Subprocesos creados:
{process_events_str}

🍯 Accesos a archivos HONEYPOT (credenciales falsas plantadas):
{honeypot_str}

=== INSTRUCCIONES ===

Analiza si el comportamiento es consistente con la descripción declarada.

Considera como sospechoso:
- Acceder a archivos fuera del scope declarado (especialmente ~/.aws, ~/.ssh, /etc/passwd)
- Cualquier acceso a archivos honeypot (SIEMPRE es crítico)
- Intentos de conexión de red si no se declara esa funcionalidad
- Crear subprocesos inesperados (curl, wget, bash, sh)
- Acceder a /proc, /sys, o información del sistema host

Considera como normal:
- Leer node_modules, archivos .node del runtime
- Acceder a /app (directorio del package)
- Leer librerías del sistema (libc, libnode, etc.)
- Crear sockets Unix locales (para IPC de Node.js)

Responde ÚNICAMENTE con este JSON:
{{
  "risk_score": <número 0-100>,
  "risk_level": "<safe|low|medium|high|critical>",
  "findings": [
    {{
      "severity": "<critical|high|medium|low|info>",
      "type": "<unauthorized_file_access|network_exfiltration|remote_code_execution|honeypot_access|suspicious_process|info_gathering|other>",
      "description": "<descripción clara y concisa>"
    }}
  ],
  "expected_behavior": [
    "<comportamiento legítimo observado que sí coincide con la descripción>"
  ],
  "recommendation": "<SAFE TO INSTALL|REVIEW MANUALLY|DO NOT INSTALL>",
  "reasoning": "<explicación de 1-3 oraciones del análisis>"
}}
"""


def _format_file_events(behavior: BehaviorReport) -> str:
    if not behavior.file_events:
        return "  (ninguno capturado)"
    lines = []
    for e in behavior.file_events[:50]:  # Limitar para el prompt
        lines.append(f"  [{e.operation.upper()}] {e.path}")
    return "\n".join(lines)


def _format_network_events(behavior: BehaviorReport) -> str:
    if not behavior.network_events:
        return "  (ninguno — red aislada)"
    return "\n".join(
        f"  connect → {e.address}:{e.port}" for e in behavior.network_events
    )


def _format_process_events(behavior: BehaviorReport) -> str:
    if not behavior.process_events:
        return "  (ninguno además del proceso principal)"
    return "\n".join(f"  execve: {e.command}" for e in behavior.process_events)


def _format_honeypots(behavior: BehaviorReport) -> str:
    if not behavior.honeypot_accesses:
        return "  ✅ Ningún honeypot fue accedido"
    lines = []
    for path in behavior.honeypot_accesses:
        lines.append(f"  🚨 {path} FUE ACCEDIDO")
    return "\n".join(lines)


def _parse_analysis(raw: str) -> SecurityAnalysis:
    """Parsea la respuesta JSON del LLM en SecurityAnalysis."""
    clean = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', clean, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            # Fallback conservador
            return SecurityAnalysis(
                risk_score=50,
                risk_level="medium",
                findings=[
                    SecurityFinding(
                        severity="medium",
                        type="other",
                        description="No se pudo analizar el comportamiento automáticamente",
                    )
                ],
                recommendation="REVIEW MANUALLY",
                raw_analysis=raw,
            )

    findings = [
        SecurityFinding(
            severity=f.get("severity", "info"),
            type=f.get("type", "other"),
            description=f.get("description", ""),
        )
        for f in data.get("findings", [])
    ]

    return SecurityAnalysis(
        risk_score=int(data.get("risk_score", 50)),
        risk_level=data.get("risk_level", "medium"),
        findings=findings,
        expected_behavior=data.get("expected_behavior", []),
        recommendation=data.get("recommendation", "REVIEW MANUALLY"),
        raw_analysis=data.get("reasoning", ""),
    )
