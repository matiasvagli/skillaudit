"""Descarga un package npm a un directorio temporal."""

import subprocess
import tarfile
import tempfile
import shutil
from pathlib import Path

from rich.console import Console

console = Console()


def download_package(package_name: str, work_dir: Path) -> Path:
    """
    Descarga el package npm y lo extrae en work_dir/package/.
    Retorna el path al directorio extraído.
    """
    pack_dir = work_dir / "npm_pack"
    pack_dir.mkdir(parents=True, exist_ok=True)

    # npm pack descarga el .tgz del package
    result = subprocess.run(
        ["npm", "pack", package_name, "--pack-destination", str(pack_dir)],
        capture_output=True,
        text=True,
        check=True,
    )

    # La última línea de stdout es el nombre del archivo .tgz
    tgz_name = result.stdout.strip().split("\n")[-1].strip()
    tgz_path = pack_dir / tgz_name

    if not tgz_path.exists():
        # npm puede imprimir el path relativo
        candidates = list(pack_dir.glob("*.tgz"))
        if not candidates:
            raise FileNotFoundError(
                f"npm pack no generó ningún .tgz en {pack_dir}. "
                f"Stdout: {result.stdout} Stderr: {result.stderr}"
            )
        tgz_path = candidates[0]

    # Extraer el tarball
    extract_dir = work_dir / "package"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz_path, "r:gz") as tar:
        tar.extractall(extract_dir, filter="data")

    # npm pack siempre crea una carpeta llamada "package/" dentro
    inner = extract_dir / "package"
    if inner.exists():
        return inner

    return extract_dir
