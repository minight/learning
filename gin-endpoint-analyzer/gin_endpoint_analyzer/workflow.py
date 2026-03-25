"""
LangGraph workflow for systematic Go/Gin endpoint security analysis.

Architecture:
  extract_endpoints -> analyze_batch (parallel subagents per endpoint) -> verify_coverage
       ^                                                                       |
       |                                                                       v
       +-------- retry_missing (if INCOMPLETE) <------------ check_complete ---+
                                                                       |
                                                                       v (if COMPLETE)
                                                              generate_report
"""

import operator
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .extractor import Endpoint, extract_endpoints, format_endpoint_for_analysis
from .prompts import (
    ENDPOINT_ANALYZER_SYSTEM,
    ENDPOINT_ANALYZER_USER,
    REPORT_SYSTEM,
    REPORT_USER,
    VERIFIER_SYSTEM,
    VERIFIER_USER,
)

console = Console()


# --- State definition ---


def merge_analyses(left: dict, right: dict) -> dict:
    merged = left.copy()
    merged.update(right)
    return merged


class AnalysisState(TypedDict):
    codebase_path: str
    endpoints: list[Endpoint]
    # Map of endpoint_id -> analysis text
    analyses: Annotated[dict[str, str], merge_analyses]
    failed_endpoints: Annotated[list[str], operator.add]
    verification_report: str
    is_complete: bool
    retry_count: int
    max_retries: int
    final_report: str
    model_name: str


# --- Node implementations ---


def extract_node(state: AnalysisState) -> dict:
    """Extract all endpoints from the Go/Gin codebase."""
    codebase_path = state["codebase_path"]
    console.print(f"\n[bold blue]📡 Extracting endpoints from:[/] {codebase_path}")

    endpoints = extract_endpoints(codebase_path)
    console.print(f"[bold green]✓ Found {len(endpoints)} endpoints[/]")

    for ep in endpoints:
        console.print(f"  [dim]{ep.method:6s} {ep.full_path}[/] → {ep.handler_name}")

    return {"endpoints": endpoints}


def analyze_batch_node(state: AnalysisState) -> dict:
    """Analyze each endpoint individually using LLM subagent calls.

    Each endpoint gets its own fresh LLM call (isolated context), mimicking
    the subagent pattern from the research. We process sequentially to avoid
    rate limits but each call is independent.
    """
    endpoints = state["endpoints"]
    existing_analyses = state.get("analyses", {})
    model_name = state.get("model_name", "claude-sonnet-4-20250514")

    # Only analyze endpoints we haven't successfully analyzed yet
    to_analyze = [
        ep for ep in endpoints if ep.id not in existing_analyses
    ]

    if not to_analyze:
        console.print("[yellow]No new endpoints to analyze.[/]")
        return {"analyses": {}, "failed_endpoints": []}

    llm = ChatAnthropic(model=model_name, max_tokens=4096, temperature=0)

    new_analyses: dict[str, str] = {}
    new_failures: list[str] = []

    console.print(
        f"\n[bold blue]🔍 Analyzing {len(to_analyze)} endpoints...[/]"
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing endpoints...", total=len(to_analyze))

        for i, ep in enumerate(to_analyze):
            ep_detail = format_endpoint_for_analysis(ep)
            progress.update(
                task,
                description=f"[{i+1}/{len(to_analyze)}] {ep.method} {ep.full_path}",
            )

            try:
                messages = [
                    SystemMessage(content=ENDPOINT_ANALYZER_SYSTEM),
                    HumanMessage(
                        content=ENDPOINT_ANALYZER_USER.format(
                            endpoint_details=ep_detail,
                            endpoint_id=ep.id,
                        )
                    ),
                ]
                response = llm.invoke(messages)
                new_analyses[ep.id] = response.content
                console.print(
                    f"  [green]✓[/] {ep.method:6s} {ep.full_path}"
                )
            except Exception as e:
                console.print(
                    f"  [red]✗[/] {ep.method:6s} {ep.full_path} — {e}"
                )
                new_failures.append(ep.id)

            progress.advance(task)

    console.print(
        f"\n[bold]Batch complete:[/] {len(new_analyses)} analyzed, {len(new_failures)} failed"
    )

    return {"analyses": new_analyses, "failed_endpoints": new_failures}


def verify_node(state: AnalysisState) -> dict:
    """Verifier agent: checks that all endpoints have been analyzed."""
    endpoints = state["endpoints"]
    analyses = state.get("analyses", {})
    failed = state.get("failed_endpoints", [])
    model_name = state.get("model_name", "claude-sonnet-4-20250514")

    all_ep_ids = [ep.id for ep in endpoints]
    analyzed_ids = list(analyses.keys())
    # Failed endpoints that haven't been retried successfully
    still_failed = [eid for eid in failed if eid not in analyses]

    console.print(f"\n[bold blue]🔎 Verifying coverage...[/]")
    console.print(
        f"  Discovered: {len(all_ep_ids)} | Analyzed: {len(analyzed_ids)} | Failed: {len(still_failed)}"
    )

    llm = ChatAnthropic(model=model_name, max_tokens=2048, temperature=0)

    messages = [
        SystemMessage(content=VERIFIER_SYSTEM),
        HumanMessage(
            content=VERIFIER_USER.format(
                total_count=len(all_ep_ids),
                all_endpoints="\n".join(f"- {eid}" for eid in all_ep_ids),
                analyzed_count=len(analyzed_ids),
                analyzed_endpoints="\n".join(f"- {eid}" for eid in analyzed_ids),
                failed_count=len(still_failed),
                failed_endpoints="\n".join(f"- {eid}" for eid in still_failed)
                if still_failed
                else "(none)",
            )
        ),
    ]

    response = llm.invoke(messages)
    verification_report = response.content

    # Determine completeness: all endpoints analyzed
    is_complete = len(analyzed_ids) >= len(all_ep_ids)

    if is_complete:
        console.print("[bold green]✓ Verification: COMPLETE — all endpoints analyzed[/]")
    else:
        missing = set(all_ep_ids) - set(analyzed_ids)
        console.print(
            f"[bold yellow]⚠ Verification: INCOMPLETE — {len(missing)} endpoints missing[/]"
        )

    return {"verification_report": verification_report, "is_complete": is_complete}


def check_complete(state: AnalysisState) -> str:
    """Conditional edge: route to report generation or retry."""
    if state.get("is_complete", False):
        return "generate_report"
    if state.get("retry_count", 0) >= state.get("max_retries", 3):
        console.print(
            "[bold red]Max retries reached. Generating report with partial coverage.[/]"
        )
        return "generate_report"
    return "retry_missing"


def retry_missing_node(state: AnalysisState) -> dict:
    """Re-attempt analysis on endpoints that failed or were missed."""
    console.print(
        f"\n[bold yellow]🔄 Retry attempt {state.get('retry_count', 0) + 1}...[/]"
    )
    # Increment retry count; the analyze_batch_node will pick up unanalyzed endpoints
    return {"retry_count": state.get("retry_count", 0) + 1}


def generate_report_node(state: AnalysisState) -> dict:
    """Generate the final comprehensive security report."""
    console.print("\n[bold blue]📝 Generating security report...[/]")
    model_name = state.get("model_name", "claude-sonnet-4-20250514")

    analyses = state.get("analyses", {})
    all_analyses_text = "\n\n---\n\n".join(
        f"### {ep_id}\n{analysis}" for ep_id, analysis in analyses.items()
    )

    llm = ChatAnthropic(model=model_name, max_tokens=8192, temperature=0)

    messages = [
        SystemMessage(content=REPORT_SYSTEM),
        HumanMessage(
            content=REPORT_USER.format(
                codebase_path=state["codebase_path"],
                date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                total_endpoints=len(state["endpoints"]),
                all_analyses=all_analyses_text,
                verification_report=state.get("verification_report", "N/A"),
            )
        ),
    ]

    response = llm.invoke(messages)
    console.print("[bold green]✓ Report generated[/]")
    return {"final_report": response.content}


# --- Graph construction ---


def build_workflow() -> StateGraph:
    """Construct the LangGraph workflow for endpoint security analysis."""
    workflow = StateGraph(AnalysisState)

    # Add nodes
    workflow.add_node("extract", extract_node)
    workflow.add_node("analyze_batch", analyze_batch_node)
    workflow.add_node("verify", verify_node)
    workflow.add_node("retry_missing", retry_missing_node)
    workflow.add_node("generate_report", generate_report_node)

    # Define edges
    workflow.set_entry_point("extract")
    workflow.add_edge("extract", "analyze_batch")
    workflow.add_edge("analyze_batch", "verify")

    # Conditional: complete -> report, incomplete -> retry
    workflow.add_conditional_edges(
        "verify",
        check_complete,
        {
            "generate_report": "generate_report",
            "retry_missing": "retry_missing",
        },
    )

    # Retry loops back to analyze_batch
    workflow.add_edge("retry_missing", "analyze_batch")

    # Report is the terminal node
    workflow.add_edge("generate_report", END)

    return workflow


def run_analysis(
    codebase_path: str,
    model_name: str = "claude-sonnet-4-20250514",
    max_retries: int = 3,
) -> AnalysisState:
    """Execute the full analysis workflow."""
    workflow = build_workflow()
    app = workflow.compile()

    initial_state: AnalysisState = {
        "codebase_path": codebase_path,
        "endpoints": [],
        "analyses": {},
        "failed_endpoints": [],
        "verification_report": "",
        "is_complete": False,
        "retry_count": 0,
        "max_retries": max_retries,
        "final_report": "",
        "model_name": model_name,
    }

    final_state = app.invoke(initial_state)
    return final_state
