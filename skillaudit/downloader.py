"""Descarga un package (npm o pip) a un directorio temporal."""

import subprocess
import tarfile
import tempfile
import shutil
import sys
from pathlib import Path

from rich.console import Console

console = Console()


def download_package(package_name: str, work_dir: Path) -> Path:
    """
    Descarga el package (npm o pip) y lo extrae en work_dir/package/.
    Retorna el path al directorio extraído.
    """
    # Intentar detectar si es un package de Python
    # (Heurística simple: si no empieza con @ y no se encuentra en npm, o si se prefiere pip)
    
    # Intentar como NPM primero (comportamiento actual)
    try:
        return _download_npm(package_name, work_dir)
    except Exception as e:
        console.print(f"   [dim]npm pack falló o no encontró el package ({e}). Intentando con pip...[/dim]")
        return _download_pip(package_name, work_dir)


def _download_npm(package_name: str, work_dir: Path) -> Path:
    pack_dir = work_dir / "npm_pack"
    pack_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["npm", "pack", package_name, "--pack-destination", str(pack_dir)],
        capture_output=True,
        text=True,
        check=True,
    )

    tgz_name = result.stdout.strip().split("\n")[-1].strip()
    tgz_path = pack_dir / tgz_name

    if not tgz_path.exists():
        candidates = list(pack_dir.glob("*.tgz"))
        if not candidates:
            raise FileNotFoundError(f"npm pack no generó ningún .tgz en {pack_dir}")
        tgz_path = candidates[0]

    extract_dir = work_dir / "package"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz_path, "r:gz") as tar:
        tar.extractall(extract_dir, filter="data")

    inner = extract_dir / "package"
    return inner if inner.exists() else extract_dir


def _download_pip(package_name: str, work_dir: Path) -> Path:
    """Descarga un package de PyPI usando pip download."""
    pack_dir = work_dir / "pip_pack"
    pack_dir.mkdir(parents=True, exist_ok=True)

    # pip download descarga el wheel o tar.gz
    subprocess.run(
        [sys.executable, "-m", "pip", "download", "--no-deps", package_name, "-d", str(pack_dir)],
        capture_output=True,
        text=True,
        check=True,
    )

    # Buscar el archivo descargado (.whl o .tar.gz)
    candidates = list(pack_dir.glob("*"))
    if not candidates:
        raise FileNotFoundError(f"pip download no descargó nada para {package_name}")
    
    pkg_file = candidates[0]
    extract_dir = work_dir / "package"
    extract_dir.mkdir(parents=True, exist_ok=True)

    if pkg_file.suffix == ".whl":
        # Wheels son archivos zip
        import zipfile
        with zipfile.ZipFile(pkg_file, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
    else:
        # tar.gz
        with tarfile.open(pkg_file, "r:*") as tar:
            tar.extractall(extract_dir)

    return extract_dir
