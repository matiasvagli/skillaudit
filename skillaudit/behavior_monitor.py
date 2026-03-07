"""Behavior Monitor — captura syscalls y accesos durante la ejecución del MCP server."""

import re
from pathlib import Path

from .models import BehaviorReport, FileEvent, NetworkEvent, ProcessEvent
from .sandbox_runner import SandboxContainer

# Paths de honeypots para detectar accesos no autorizados
HONEYPOT_PATHS = [
    "/root/.aws/credentials",
    "/root/.ssh/id_rsa",
    "/root/.ssh/authorized_keys",
    "/etc/passwd",
    "/etc/shadow",
]

# Patterns de paths sospechosos (fuera del scope de /app y /tmp)
SUSPICIOUS_PATH_PATTERNS = [
    r"/root/\.",
    r"/home/",
    r"/etc/passwd",
    r"/etc/shadow",
    r"/proc/\d+",
]


def capture_behavior(
    sandbox: SandboxContainer,
    entrypoint: str,
    driver_script_content: str,
) -> BehaviorReport:
    """
    Ejecuta el MCP server bajo strace y captura:
    - Syscalls de filesystem (open, read, write, unlink)
    - Intentos de conexión de red (connect, socket)
    - Subprocesos creados (execve)
    - Acceso a honeypots
    
    Retorna BehaviorReport con todos los eventos categorizados.
    """
    report = BehaviorReport()

    # Escribir el driver script dentro del container
    _write_driver(sandbox, driver_script_content)

    # Ejecutar bajo strace
    strace_output = _run_with_strace(sandbox, entrypoint)
    report.raw_strace = strace_output

    # Parsear events del strace
    report.file_events = _parse_file_events(strace_output)
    report.network_events = _parse_network_events(strace_output)
    report.process_events = _parse_process_events(strace_output)

    # Detectar honeypots tocados
    report.honeypot_accesses = _detect_honeypot_access(report.file_events)

    return report


def _write_driver(sandbox: SandboxContainer, script: str) -> None:
    """Escribe el driver.mjs en /tmp dentro del container."""
    # Escapar el script para pasarlo como argumento al shell
    escaped = script.replace("'", "'\\''")
    sandbox.exec_run(
        ["sh", "-c", f"cat > /tmp/driver.mjs << 'HEREDOC'\n{script}\nHEREDOC"],
    )
    # Alternativa más robusta: via tarball
    import tarfile, io
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        encoded = script.encode()
        info = tarfile.TarInfo(name="driver.mjs")
        info.size = len(encoded)
        tar.addfile(info, io.BytesIO(encoded))
    sandbox._container.put_archive("/tmp", buf.getvalue())


def _run_with_strace(sandbox: SandboxContainer, entrypoint: str) -> str:
    """Ejecuta el driver bajo strace y captura el output."""
    exit_code, output = sandbox.exec_run(
        [
            "strace",
            "-f",                                      # Seguir child processes
            "-e", "trace=file,network,process",        # Solo syscalls relevantes
            "-s", "256",                               # Strings de hasta 256 chars
            "-o", "/tmp/strace.log",                   # Output a archivo
            "node", "/tmp/driver.mjs",
        ],
        # strace puede tardar hasta SANDBOX_TIMEOUT segundos
    )

    # Leer el log de strace
    _, strace_bytes = sandbox.exec_run(["cat", "/tmp/strace.log"])
    return strace_bytes.decode("utf-8", errors="replace") if strace_bytes else ""


def _parse_file_events(strace: str) -> list[FileEvent]:
    """Extrae eventos de filesystem del strace output."""
    events = []
    # Patterns: openat(AT_FDCWD, "/ruta", ...) = fd
    open_pattern = re.compile(r'open(?:at)?\(.*?"(/[^"]+)".*?(?:O_RDONLY|O_WRONLY|O_RDWR|O_CREAT)')
    write_pattern = re.compile(r'write\(\d+,\s*".*?"')
    unlink_pattern = re.compile(r'unlink(?:at)?\(.*?"(/[^"]+)"')

    seen = set()
    for line in strace.split("\n"):
        m = open_pattern.search(line)
        if m:
            path = m.group(1)
            op = "write" if "O_WRONLY" in line or "O_RDWR" in line or "O_CREAT" in line else "read"
            key = (path, op)
            if key not in seen:
                seen.add(key)
                events.append(FileEvent(path=path, operation=op))
            continue

        m = unlink_pattern.search(line)
        if m:
            path = m.group(1)
            key = (path, "unlink")
            if key not in seen:
                seen.add(key)
                events.append(FileEvent(path=path, operation="unlink"))

    return events


def _parse_network_events(strace: str) -> list[NetworkEvent]:
    """Extrae intentos de conexión de red del strace output."""
    events = []
    # pattern: connect(fd, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("1.2.3.4")}, 16)
    connect_pattern = re.compile(
        r'connect\(\d+.*?sin_addr=inet_addr\("([^"]+)"\).*?sin_port=htons\((\d+)\)'
    )
    connect_pattern2 = re.compile(
        r'connect\(\d+.*?sin_port=htons\((\d+)\).*?sin_addr=inet_addr\("([^"]+)"\)'
    )

    seen = set()
    for line in strace.split("\n"):
        m = connect_pattern.search(line)
        if m:
            addr, port = m.group(1), int(m.group(2))
        else:
            m = connect_pattern2.search(line)
            if m:
                port, addr = int(m.group(1)), m.group(2)
            else:
                continue

        key = (addr, port)
        if key not in seen:
            seen.add(key)
            events.append(NetworkEvent(address=addr, port=port))

    return events


def _parse_process_events(strace: str) -> list[ProcessEvent]:
    """Extrae subprocesos creados (execve)."""
    events = []
    execve_pattern = re.compile(r'execve\("([^"]+)"')
    seen = set()
    for line in strace.split("\n"):
        m = execve_pattern.search(line)
        if m:
            cmd = m.group(1)
            if cmd not in seen and cmd not in ("/usr/bin/node", "/usr/local/bin/node"):
                seen.add(cmd)
                events.append(ProcessEvent(command=cmd))
    return events


def _detect_honeypot_access(file_events: list[FileEvent]) -> list[str]:
    """Retorna los paths de honeypots que fueron accedidos."""
    accessed = []
    for event in file_events:
        if event.path in HONEYPOT_PATHS:
            accessed.append(event.path)
    return list(set(accessed))
