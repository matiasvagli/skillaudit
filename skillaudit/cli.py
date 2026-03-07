"""CLI principal de SkillAudit — orquesta todo el pipeline de auditoría."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import print as rprint
from rich.text import Text

from .config import config
from .downloader import download_package
from .extractor import extract_metadata
from .scenario_generator import generate_scenarios
from .sandbox_runner import create_sandbox
from .mcp_executor import run_scenarios, _build_driver_script, _discover_entrypoint
from .behavior_monitor import capture_behavior
from .log_analyzer import analyze_behavior
from .report_generator import generate_report

console = Console()

SEVERITY_STYLES = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "blue",
    "info": "dim",
}

RISK_STYLES = {
    "safe": "bold green",
    "low": "green",
    "medium": "yellow",
    "high": "bold red",
    "critical": "bold red on white",
}


@click.group()
@click.version_option("0.1.0", prog_name="skillaudit")
def cli():
    """🔍 SkillAudit — Sandbox de seguridad para MCP servers y AI skills."""
    pass


@cli.command()
@click.argument("package_name")
@click.option(
    "--output-dir",
    "-o",
    default="./skillaudit-reports",
    show_default=True,
    help="Directorio donde guardar los reportes",
)
@click.option(
    "--ai-provider",
    default=None,
    help="Proveedor de IA: gemini, openai, anthropic (default: env SKILLAUDIT_AI_PROVIDER)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Mostrar output detallado del strace y logs del MCP server",
)
def test(package_name: str, output_dir: str, ai_provider: str | None, verbose: bool):
    """
    Audita un MCP server en un sandbox Docker aislado.

    \b
    Ejemplos:
      skillaudit test @modelcontextprotocol/server-filesystem
      skillaudit test @some/mcp-server --output-dir ./reports
    """
    if ai_provider:
        config.AI_PROVIDER = ai_provider

    # Validar config
    try:
        config.validate()
    except ValueError as e:
        console.print(f"[bold red]❌ Error de configuración:[/bold red] {e}")
        sys.exit(1)

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]🔍 Auditando[/bold cyan] [bold white]{package_name}[/bold white]",
            border_style="cyan",
        )
    )
    console.print()

    output_path = Path(output_dir)

    with tempfile.TemporaryDirectory(prefix="skillaudit-") as tmpdir:
        work_dir = Path(tmpdir)

        # ── PASO 1: Descargar ─────────────────────────────────────────────
        with _step("📦 Descargando package..."):
            try:
                package_dir = download_package(package_name, work_dir)
            except Exception as e:
                _fail(f"Error descargando {package_name}: {e}")
                sys.exit(1)
        console.print(f"   [dim]→ {package_dir}[/dim]")

        # ── PASO 2: Extraer metadata ───────────────────────────────────────
        with _step("📋 Leyendo metadata del package..."):
            try:
                metadata = extract_metadata(package_dir)
            except Exception as e:
                _fail(f"Error leyendo metadata: {e}")
                sys.exit(1)

        console.print(f"   [green]✓[/green] [bold]{metadata.package_name}@{metadata.version}[/bold]")
        console.print(f"   [dim]\"{metadata.short_description}\"[/dim]")
        if metadata.tools:
            console.print(f"   [dim]Tools declaradas: {', '.join(t.name for t in metadata.tools)}[/dim]")
        console.print()

        # ── PASO 3: Generar scenarios con IA ─────────────────────────────
        with _step(f"🤖 Generando test scenarios ({config.AI_PROVIDER})..."):
            try:
                scenarios = generate_scenarios(metadata)
            except Exception as e:
                _fail(f"Error generando scenarios: {e}")
                sys.exit(1)

        console.print(f"   [green]✓[/green] Generados [bold]{len(scenarios)}[/bold] test cases")
        for s in scenarios:
            console.print(f"   [dim]→ {s.name} ({s.tool})[/dim]")
        console.print()

        # ── PASO 4: Sandbox + Ejecución + Monitoring ──────────────────────
        console.print("🐳 [bold]Iniciando sandbox Docker...[/bold]")

        try:
            with create_sandbox(package_dir) as sandbox:
                console.print(f"   [green]✓[/green] Container [bold]{sandbox.id}[/bold] creado")
                console.print(f"   [dim]→ Red: aislada (--network none)[/dim]")
                console.print(f"   [dim]→ Honeypots: /root/.aws/credentials, /root/.ssh/id_rsa[/dim]")
                console.print()

                # Descubrir entrypoint
                entrypoint = metadata.entrypoint or _discover_entrypoint(sandbox)
                console.print(f"   [dim]Entrypoint: {entrypoint}[/dim]")
                console.print()

                # Construir driver script para el executor
                messages_for_driver = _build_messages_for_driver(scenarios, metadata)
                driver_script = _build_driver_script(entrypoint, messages_for_driver)

                # ── PASO 5: Capturar comportamiento ───────────────────────
                console.print("🔬 [bold]Ejecutando con monitor de comportamiento...[/bold]")
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    task = progress.add_task("   Ejecutando bajo strace...", total=None)
                    try:
                        behavior = capture_behavior(sandbox, entrypoint, driver_script)
                        progress.update(task, description="   ✅ Captura completada")
                    except Exception as e:
                        progress.update(task, description=f"   ⚠️  Error en monitoring: {e}")
                        from .models import BehaviorReport
                        behavior = BehaviorReport(raw_stderr=str(e))

                # Resultados del executor (obtenemos del behavior report)
                call_results, _, _ = run_scenarios(sandbox, entrypoint, scenarios)

                console.print()
                _print_behavior_summary(behavior, verbose)

        except RuntimeError as e:
            _fail(str(e))
            sys.exit(1)

        console.print()

        # ── PASO 6: Análisis con IA ────────────────────────────────────────
        with _step(f"🧠 Analizando con IA ({config.AI_PROVIDER})..."):
            try:
                analysis = analyze_behavior(metadata, behavior)
            except Exception as e:
                _fail(f"Error en análisis de IA: {e}")
                sys.exit(1)

        console.print()

        # ── PASO 7: Reporte ───────────────────────────────────────────────
        with _step("📊 Generando reporte..."):
            json_path, md_path = generate_report(
                metadata, scenarios, call_results, behavior, analysis, output_path
            )

        console.print()

        # ── RESULTADO FINAL ───────────────────────────────────────────────
        _print_final_report(analysis, json_path, md_path)


def _build_messages_for_driver(scenarios, metadata):
    """Importación lazy para evitar circular imports."""
    from .mcp_executor import _build_jsonrpc_sequence
    return _build_jsonrpc_sequence(scenarios)


def _print_behavior_summary(behavior, verbose: bool) -> None:
    """Muestra un resumen del comportamiento capturado."""
    table = Table(title="Comportamiento Observado", border_style="dim")
    table.add_column("Categoría", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Detalle", style="dim")

    table.add_row(
        "📁 Filesystem",
        str(len(behavior.file_events)),
        ", ".join(set(e.operation for e in behavior.file_events[:5])) or "—",
    )
    table.add_row(
        "🌐 Red",
        str(len(behavior.network_events)),
        "Aislada — sin acceso" if not behavior.network_events else
        ", ".join(f"{e.address}:{e.port}" for e in behavior.network_events[:3]),
    )
    table.add_row(
        "⚙️ Procesos",
        str(len(behavior.process_events)),
        ", ".join(e.command for e in behavior.process_events[:3]) or "—",
    )

    honeypot_style = "bold red" if behavior.honeypot_accesses else "green"
    table.add_row(
        "🍯 Honeypots",
        str(len(behavior.honeypot_accesses)),
        Text(
            "🚨 " + ", ".join(behavior.honeypot_accesses) if behavior.honeypot_accesses else "✅ Ninguno",
            style=honeypot_style,
        ),
    )
    console.print(table)

    if verbose and behavior.raw_strace:
        console.print("\n[dim]── strace output (primeras 2000 chars) ──[/dim]")
        console.print(f"[dim]{behavior.raw_strace[:2000]}[/dim]")


def _print_final_report(analysis, json_path: Path, md_path: Path) -> None:
    """Muestra el reporte final de seguridad en la terminal."""
    risk_style = RISK_STYLES.get(analysis.risk_level, "yellow")

    console.print(
        Panel.fit(
            f"[bold]Risk Score:[/bold] [{risk_style}]{analysis.risk_score}/100 — {analysis.risk_level.upper()}[/{risk_style}]",
            title="[bold]📊 SECURITY ANALYSIS[/bold]",
            border_style="cyan",
        )
    )
    console.print()

    if analysis.findings:
        console.print("[bold]🔎 Findings:[/bold]")
        for finding in analysis.findings:
            style = SEVERITY_STYLES.get(finding.severity, "white")
            icon = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🔵",
                "info": "ℹ️",
            }.get(finding.severity, "•")
            console.print(
                f"  {icon} [{style}][{finding.severity.upper()}][/{style}] "
                f"{finding.description}"
            )
        console.print()

    if analysis.expected_behavior:
        console.print("[bold]✅ Comportamiento esperado confirmado:[/bold]")
        for eb in analysis.expected_behavior:
            console.print(f"  [green]•[/green] {eb}")
        console.print()

    if analysis.raw_analysis:
        console.print(f"[dim]{analysis.raw_analysis}[/dim]")
        console.print()

    # Recomendación final
    rec_styles = {
        "SAFE TO INSTALL": ("✅", "bold green"),
        "REVIEW MANUALLY": ("⚠️", "bold yellow"),
        "DO NOT INSTALL": ("❌", "bold red"),
    }
    icon, style = rec_styles.get(analysis.recommendation, ("⚠️", "yellow"))
    console.print(
        Panel.fit(
            f"[{style}]{icon} {analysis.recommendation}[/{style}]",
            border_style=style.split()[-1],
        )
    )

    console.print()
    console.print(f"[dim]📄 JSON:[/dim] [link=file://{json_path}]{json_path}[/link]")
    console.print(f"[dim]📝 Markdown:[/dim] [link=file://{md_path}]{md_path}[/link]")
    console.print()


class _step:
    """Context manager para mostrar un spinner en pasos del pipeline."""
    def __init__(self, message: str):
        self._message = message
        self._progress = None
        self._task_id = None

    def __enter__(self):
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        )
        self._progress.__enter__()
        self._task_id = self._progress.add_task(self._message, total=None)
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self._progress.update(
                self._task_id,
                description=self._message.replace("...", " ✓"),
            )
        self._progress.__exit__(exc_type, *_)


def _fail(msg: str) -> None:
    console.print(f"[bold red]❌ {msg}[/bold red]")
