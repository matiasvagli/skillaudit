"""Sandbox Docker — crea y destruye contenedores aislados para ejecutar MCP servers."""

import docker
import tarfile
import io
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from .config import config

# Honeypot credentials falsas para detectar si la skill los accede
HONEYPOT_AWS = """\
[default]
aws_access_key_id = AKIAIOSFODNN7HONEYPOT
aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYHONEYPOT
"""

HONEYPOT_SSH = """\
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAAAAAAAAA HONEYPOT KEY DO NOT USE
-----END OPENSSH PRIVATE KEY-----
"""


class SandboxContainer:
    """Wrapper alrededor de un contenedor Docker de sandbox."""

    def __init__(self, container, package_dir: Path):
        self._container = container
        self.package_dir = package_dir

    @property
    def id(self) -> str:
        return self._container.id[:12]

    def exec_run(self, cmd: list[str], **kwargs) -> tuple[int, bytes]:
        """Ejecuta un comando dentro del contenedor."""
        result = self._container.exec_run(cmd, **kwargs)
        return result.exit_code, result.output

    def stop(self) -> None:
        try:
            self._container.stop(timeout=5)
            self._container.remove(force=True)
        except Exception:
            pass


def _create_tar_stream(content: str, arcname: str) -> bytes:
    """Crea un tarball en memoria para `put_archive`."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        encoded = content.encode()
        info = tarfile.TarInfo(name=arcname)
        info.size = len(encoded)
        tar.addfile(info, io.BytesIO(encoded))
    return buf.getvalue()


@contextmanager
def create_sandbox(package_dir: Path) -> Generator[SandboxContainer, None, None]:
    """
    Context manager que crea el sandbox Docker, lo entrega y lo destruye al salir.

    El contenedor tiene:
    - Red DESACTIVADA (--network none)
    - /tmp con permisos de escritura
    - Honeypot files en /root/.aws/ y /root/.ssh/
    - Package npm montado en /app
    - strace disponible para monitoring
    """
    client = docker.from_env()

    # Verificar que la imagen existe
    try:
        client.images.get(config.SANDBOX_IMAGE)
    except docker.errors.ImageNotFound:
        raise RuntimeError(
            f"Imagen Docker '{config.SANDBOX_IMAGE}' no encontrada.\n"
            "Buildéala con: cd skillaudit/sandbox && docker build -t skillaudit-sandbox:latest ."
        )

    IMAGE_NAME = config.SANDBOX_IMAGE
    container = client.containers.run(
        image=IMAGE_NAME,
        command="sleep infinity",  # Mantenemos el container vivo; ejecutamos via exec
        network_mode="none",       # Sin red — aislamiento total
        volumes={
            str(package_dir): {
                "bind": "/app",
                "mode": "ro",       # Package solo lectura
            }
        },
        working_dir="/app",
        mem_limit="256m",
        cpu_period=100_000,
        cpu_quota=50_000,           # 50% de 1 CPU
        security_opt=["no-new-privileges"],
        detach=True,
        remove=False,               # Lo removemos manualmente en stop()
        environment={
            "HOME": "/root",
            "NODE_ENV": "production",
        },
    )

    sandbox = SandboxContainer(container, package_dir)

    try:
        # Instalar dependencias NPM dentro del sandbox
        _install_npm_deps(container)
        # Instalar dependencias Python dentro del sandbox
        _install_python_deps(container)
        # Inyectar honeypots
        _inject_honeypots(container)
        yield sandbox
    finally:
        sandbox.stop()


def _install_npm_deps(container) -> None:
    """npm install dentro del container (sin red — usa el package bundleado)."""
    # Intentamos con --prefer-offline primero, limitando a 15 segundos para evitar cuelgues sin red
    exit_code, output = container.exec_run(
        ["timeout", "15", "npm", "install", "--prefer-offline", "--production"],
        workdir="/app",
    )
    # Si falla (package no tiene deps bundleadas, lo ignoramos)
    # El MCP server podría no necesitar install si ya tiene node_modules


def _inject_honeypots(container) -> None:
    """Inyecta archivos falsos de credenciales para detectar accesos no autorizados."""
    # ~/.aws/credentials
    container.exec_run(["mkdir", "-p", "/root/.aws"])
    aws_tar = _create_tar_stream(HONEYPOT_AWS, "credentials")
    container.put_archive("/root/.aws", aws_tar)

    # ~/.ssh/id_rsa
    container.exec_run(["mkdir", "-p", "/root/.ssh"])
    container.exec_run(["chmod", "700", "/root/.ssh"])
    ssh_tar = _create_tar_stream(HONEYPOT_SSH, "id_rsa")
    container.put_archive("/root/.ssh", ssh_tar)
    container.exec_run(["chmod", "600", "/root/.ssh/id_rsa"])


def _install_python_deps(container) -> None:
    """pip install dentro del container (sin red — intenta usar cache o bundle)."""
    # Intentar instalar desde pyproject.toml o requirements.txt si existen
    # Nota: sin red esto fallará a menos que el package sea un wheel ya funcional
    # o hayamos montado las deps. Pero por ahora, intentamos lo básico.
    container.exec_run(
        ["timeout", "30", "pip", "install", ".", "--prefer-offline", "--no-input"],
        workdir="/app",
    )
