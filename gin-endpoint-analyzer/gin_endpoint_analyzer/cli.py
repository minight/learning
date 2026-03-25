"""CLI interface for the Gin Endpoint Security Analyzer."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from .extractor import extract_endpoints, format_endpoint_for_analysis
from .workflow import run_analysis

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Gin Endpoint Security Analyzer — LangGraph-powered security analysis for Go/Gin codebases."""
    pass


@main.command()
@click.argument("codebase_path", type=click.Path(exists=True, file_okay=False))
def extract(codebase_path: str):
    """Extract and list all Gin endpoints from a Go codebase (no LLM calls)."""
    codebase_path = os.path.abspath(codebase_path)
    endpoints = extract_endpoints(codebase_path)

    if not endpoints:
        console.print("[yellow]No Gin endpoints found.[/]")
        return

    console.print(f"\n[bold]Found {len(endpoints)} endpoints:[/]\n")
    for ep in endpoints:
        chain_str = " → ".join(ep.call_chain) if ep.call_chain else "(no chain)"
        console.print(
            f"  [cyan]{ep.method:6s}[/] [white]{ep.full_path:40s}[/] "
            f"[dim]handler=[/]{ep.handler_name} [dim]chain=[/]{chain_str}"
        )


@main.command()
@click.argument("codebase_path", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--model",
    "-m",
    default="claude-sonnet-4-20250514",
    help="Anthropic model to use for analysis.",
)
@click.option(
    "--max-retries",
    "-r",
    default=3,
    help="Max retry attempts for failed endpoint analyses.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output file for the report (default: stdout + .md file).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Extract endpoints and show what would be analyzed, without calling the LLM.",
)
def analyze(codebase_path: str, model: str, max_retries: int, output: str, dry_run: bool):
    """Run full security analysis on all Gin endpoints in a Go codebase."""
    codebase_path = os.path.abspath(codebase_path)

    if dry_run:
        endpoints = extract_endpoints(codebase_path)
        console.print(
            Panel(
                f"[bold]Dry Run — Gin Endpoint Security Analyzer[/]\n"
                f"Codebase: {codebase_path}\n"
                f"Model: {model}\n"
                f"Endpoints found: {len(endpoints)}",
                title="Configuration",
                border_style="yellow",
            )
        )
        for i, ep in enumerate(endpoints, 1):
            chain = " → ".join(ep.call_chain)
            console.print(
                f"  [{i:3d}] [cyan]{ep.method:6s}[/] {ep.full_path:40s} "
                f"[dim]chain=[/]{chain} [dim]({len(ep.call_chain_bodies)} functions)[/]"
            )
        console.print(f"\n[bold]Would analyze {len(endpoints)} endpoints with model {model}[/]")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print(
            "[bold red]Error:[/] ANTHROPIC_API_KEY environment variable not set."
        )
        sys.exit(1)

    console.print(
        Panel(
            f"[bold]Gin Endpoint Security Analyzer[/]\n"
            f"Codebase: {codebase_path}\n"
            f"Model: {model}\n"
            f"Max retries: {max_retries}",
            title="Configuration",
            border_style="blue",
        )
    )

    # Run the LangGraph workflow
    final_state = run_analysis(
        codebase_path=codebase_path,
        model_name=model,
        max_retries=max_retries,
    )

    report = final_state.get("final_report", "")

    if not report:
        console.print("[bold red]No report generated.[/]")
        sys.exit(1)

    # Determine output path
    if output is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output = f"security_report_{timestamp}.md"

    Path(output).write_text(report)
    console.print(f"\n[bold green]✓ Report saved to:[/] {output}")

    # Print summary stats
    endpoints = final_state.get("endpoints", [])
    analyses = final_state.get("analyses", {})
    console.print(
        Panel(
            f"Endpoints discovered: {len(endpoints)}\n"
            f"Endpoints analyzed: {len(analyses)}\n"
            f"Coverage: {len(analyses)}/{len(endpoints)} "
            f"({100 * len(analyses) / max(len(endpoints), 1):.0f}%)\n"
            f"Complete: {'Yes' if final_state.get('is_complete') else 'No'}",
            title="Summary",
            border_style="green",
        )
    )


@main.command()
@click.argument("codebase_path", type=click.Path(exists=True, file_okay=False))
@click.argument("endpoint_id")
@click.option(
    "--model",
    "-m",
    default="claude-sonnet-4-20250514",
    help="Anthropic model to use.",
)
def analyze_one(codebase_path: str, endpoint_id: str, model: str):
    """Analyze a single endpoint by its ID (e.g., 'GET /api/v1/users')."""
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage

    from .prompts import ENDPOINT_ANALYZER_SYSTEM, ENDPOINT_ANALYZER_USER

    codebase_path = os.path.abspath(codebase_path)
    endpoints = extract_endpoints(codebase_path)

    target = None
    for ep in endpoints:
        if ep.id == endpoint_id:
            target = ep
            break

    if not target:
        console.print(f"[red]Endpoint '{endpoint_id}' not found.[/]")
        console.print("Available endpoints:")
        for ep in endpoints:
            console.print(f"  {ep.id}")
        sys.exit(1)

    ep_detail = format_endpoint_for_analysis(target)
    llm = ChatAnthropic(model=model, max_tokens=4096, temperature=0)

    messages = [
        SystemMessage(content=ENDPOINT_ANALYZER_SYSTEM),
        HumanMessage(
            content=ENDPOINT_ANALYZER_USER.format(
                endpoint_details=ep_detail,
                endpoint_id=target.id,
            )
        ),
    ]

    console.print(f"[bold blue]Analyzing: {target.id}[/]\n")
    response = llm.invoke(messages)
    console.print(response.content)


if __name__ == "__main__":
    main()
