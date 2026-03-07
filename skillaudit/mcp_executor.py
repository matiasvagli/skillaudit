"""MCP Executor — envía llamadas JSON-RPC sintéticas al MCP server dentro del sandbox."""
from __future__ import annotations


import json
import threading
import time
from typing import Any

from .models import TestScenario
from .sandbox_runner import SandboxContainer

# Timeout por llamada individual al MCP server
CALL_TIMEOUT_SECONDS = 20


class MCPCallResult:
    def __init__(self, scenario: TestScenario, response: dict | None, error: str = ""):
        self.scenario = scenario
        self.response = response
        self.error = error
        self.success = response is not None and "error" not in response


def run_scenarios(
    sandbox: SandboxContainer,
    entrypoint: str,
    scenarios: list[TestScenario],
) -> tuple[list[MCPCallResult], str, str]:
    """
    Ejecuta el MCP server y le envía los scenarios como llamadas JSON-RPC.

    Retorna:
        - Lista de MCPCallResult
        - stdout completo capturado
        - stderr completo capturado
    """
    if not entrypoint:
        entrypoint = _discover_entrypoint(sandbox)

    results: list[MCPCallResult] = []

    # Construimos la secuencia de mensajes JSON-RPC para enviar al server
    messages = _build_jsonrpc_sequence(scenarios)
    input_data = "\n".join(json.dumps(m) for m in messages) + "\n"

    # Ejecutamos el MCP server con toda la entrada de golpe (stdin pipe)
    exit_code, raw_output = sandbox.exec_run(
        ["node", entrypoint],
        stdin=True,
        socket=False,
    )

    # Alternativa: ejecutar via shell con stdin heredoc
    # Usamos un script Python dentro del container para manejar el protocolo stdio
    stdin_script = _build_driver_script(entrypoint, messages)
    exit_code, raw_output = sandbox.exec_run(
        ["node", "--input-type=module", "-e", stdin_script],
    )

    stdout_str = raw_output.decode("utf-8", errors="replace") if raw_output else ""

    # Parsear las respuestas JSON-RPC del stdout
    results = _parse_responses(scenarios, stdout_str)

    return results, stdout_str, ""


def _discover_entrypoint(sandbox: SandboxContainer) -> str:
    """Intenta descubrir el entrypoint del MCP server en /app."""
    _, output = sandbox.exec_run(["find", "/app", "-name", "*.js", "-not", "-path", "*/node_modules/*", "-maxdepth", "3"])
    files = output.decode("utf-8", errors="replace").strip().split("\n")
    for priority in ["dist/index.js", "src/index.js", "index.js", "build/index.js"]:
        for f in files:
            if f.endswith(priority.replace("/", "/")):
                return f.strip()
    return files[0].strip() if files else "index.js"


def _build_jsonrpc_sequence(scenarios: list[TestScenario]) -> list[dict[str, Any]]:
    """Construye la secuencia completa de mensajes JSON-RPC para el MCP server."""
    msgs = [
        # 1. Initialize handshake
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "skillaudit", "version": "0.1.0"},
            },
        },
        # 2. Confirmed initialized
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        # 3. Listar tools disponibles
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    ]

    # 4. Llamar cada scenario
    for i, scenario in enumerate(scenarios):
        msgs.append({
            "jsonrpc": "2.0",
            "id": i + 10,  # IDs desde 10 para no colisionar
            "method": "tools/call",
            "params": {
                "name": scenario.tool,
                "arguments": scenario.args,
            },
        })

    return msgs


def _build_driver_script(entrypoint: str, messages: list[dict]) -> str:
    """Script Node.js que actúa como cliente MCP usando stdio."""
    messages_json = json.dumps(messages)
    return f"""
import {{ spawn }} from 'child_process';

const messages = {messages_json};
const server = spawn('node', ['{entrypoint}'], {{
  stdio: ['pipe', 'pipe', 'pipe'],
  cwd: '/app',
}});

let buffer = '';
server.stdout.on('data', (chunk) => {{
  process.stdout.write(chunk);
  buffer += chunk.toString();
}});
server.stderr.on('data', (chunk) => {{
  process.stderr.write(chunk);
}});

// Enviar mensajes con pequeño delay entre cada uno
let idx = 0;
function sendNext() {{
  if (idx >= messages.length) {{
    setTimeout(() => {{ server.kill(); process.exit(0); }}, 2000);
    return;
  }}
  const msg = messages[idx++];
  server.stdin.write(JSON.stringify(msg) + '\\n');
  setTimeout(sendNext, 300);
}}

server.on('spawn', () => setTimeout(sendNext, 500));
server.on('error', (e) => console.error('spawn error:', e));
setTimeout(() => {{ server.kill(); process.exit(0); }}, {CALL_TIMEOUT_SECONDS * 1000});
"""


def _parse_responses(scenarios: list[TestScenario], stdout: str) -> list[MCPCallResult]:
    """Parsea las respuestas JSON-RPC del stdout del MCP server."""
    responses: dict[int, dict] = {}
    for line in stdout.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if "id" in obj:
                responses[obj["id"]] = obj
        except json.JSONDecodeError:
            pass

    results = []
    for i, scenario in enumerate(scenarios):
        response_id = i + 10
        response = responses.get(response_id)
        error = ""
        if response and "error" in response:
            error = str(response["error"])
        results.append(
            MCPCallResult(scenario=scenario, response=response, error=error)
        )
    return results
