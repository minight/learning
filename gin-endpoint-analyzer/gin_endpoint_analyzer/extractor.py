"""
Static analysis extractor for Go/Gin endpoints.

Walks a Go codebase to find:
1. Gin router group definitions and route registrations
2. Handler function bodies
3. Call chains from handler -> internal functions -> sinks (DB, exec, file I/O, etc.)
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FunctionDef:
    name: str
    file: str
    start_line: int
    end_line: int
    body: str
    package: str


@dataclass
class Endpoint:
    method: str  # GET, POST, PUT, DELETE, etc.
    path: str
    handler_name: str
    handler_file: str
    handler_body: str
    group_prefix: str = ""
    full_path: str = ""
    call_chain: list[str] = field(default_factory=list)
    call_chain_bodies: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.full_path = self.group_prefix.rstrip("/") + "/" + self.path.lstrip("/")
        self.full_path = self.full_path.replace("//", "/")

    @property
    def id(self) -> str:
        return f"{self.method} {self.full_path}"


def find_go_files(codebase_path: str) -> list[str]:
    go_files = []
    for root, _, files in os.walk(codebase_path):
        # Skip vendor and test directories
        if "vendor" in root.split(os.sep) or ".git" in root.split(os.sep):
            continue
        for f in files:
            if f.endswith(".go"):
                go_files.append(os.path.join(root, f))
    return go_files


def extract_package(content: str) -> str:
    m = re.search(r"^package\s+(\w+)", content, re.MULTILINE)
    return m.group(1) if m else ""


def extract_functions(file_path: str, content: str) -> dict[str, FunctionDef]:
    """Extract all function definitions from a Go file."""
    functions: dict[str, FunctionDef] = {}
    pkg = extract_package(content)
    lines = content.split("\n")

    # Match both standalone functions and method receivers
    func_pattern = re.compile(
        r"^func\s+(?:\(\s*\w+\s+\*?\w+\s*\)\s+)?(\w+)\s*\("
    )

    for i, line in enumerate(lines):
        m = func_pattern.match(line)
        if not m:
            continue
        func_name = m.group(1)
        start = i
        # Find the end of the function by brace counting
        brace_count = 0
        started = False
        end = i
        for j in range(i, len(lines)):
            brace_count += lines[j].count("{") - lines[j].count("}")
            if "{" in lines[j]:
                started = True
            if started and brace_count <= 0:
                end = j
                break
        body = "\n".join(lines[start : end + 1])
        functions[func_name] = FunctionDef(
            name=func_name,
            file=file_path,
            start_line=start + 1,
            end_line=end + 1,
            body=body,
            package=pkg,
        )
    return functions


def extract_router_groups(content: str) -> dict[str, str]:
    """Extract router group variable names and their fully-resolved path prefixes.

    Handles nested groups like:
        api := r.Group("/api/v1")
        admin := api.Group("/admin")
    Resolves admin -> "/api/v1/admin"
    """
    group_map: dict[str, str] = {}
    # e.g., admin := api.Group("/admin")
    pattern = re.compile(r"(\w+)\s*:?=\s*(\w+)\.Group\(\s*\"([^\"]*)\"\s*\)")
    for m in pattern.finditer(content):
        var_name = m.group(1)
        parent_var = m.group(2)
        path = m.group(3)
        # Resolve parent prefix if it's another group
        parent_prefix = group_map.get(parent_var, "")
        full_prefix = parent_prefix.rstrip("/") + "/" + path.lstrip("/")
        full_prefix = full_prefix.replace("//", "/")
        group_map[var_name] = full_prefix
    return group_map


def extract_routes(content: str, groups: dict[str, str]) -> list[dict]:
    """Extract route registrations: router.METHOD(path, handler)."""
    routes = []
    methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "Any"]
    group_map = groups

    for method in methods:
        # Match: varName.METHOD("path", handlerFunc) or varName.METHOD("path", pkg.HandlerFunc)
        pattern = re.compile(
            rf"(\w+)\.{method}\(\s*\"([^\"]*)\"\s*,\s*([\w.]+)"
        )
        for m in pattern.finditer(content):
            router_var = m.group(1)
            path = m.group(2)
            handler = m.group(3)
            prefix = group_map.get(router_var, "")
            http_method = method.upper() if method != "Any" else "ANY"
            routes.append({
                "method": http_method,
                "path": path,
                "handler": handler,
                "group_prefix": prefix,
                "router_var": router_var,
            })
    return routes


def resolve_handler_name(handler_ref: str) -> str:
    """Strip package prefix from handler reference: pkg.Handler -> Handler."""
    if "." in handler_ref:
        return handler_ref.split(".")[-1]
    return handler_ref


def trace_call_chain(
    func_name: str,
    all_functions: dict[str, FunctionDef],
    visited: set[str] | None = None,
    max_depth: int = 10,
) -> list[str]:
    """Recursively trace function calls from a handler to find the call chain."""
    if visited is None:
        visited = set()
    if func_name in visited or len(visited) >= max_depth:
        return []
    visited.add(func_name)

    chain = [func_name]
    func_def = all_functions.get(func_name)
    if not func_def:
        return chain

    # Find function calls in the body
    call_pattern = re.compile(r"(?:\w+\.)?(\w+)\(")
    for m in call_pattern.finditer(func_def.body):
        callee = m.group(1)
        # Only trace functions we have definitions for (internal calls)
        if callee in all_functions and callee not in visited:
            chain.extend(trace_call_chain(callee, all_functions, visited, max_depth))

    return chain


def extract_endpoints(codebase_path: str) -> list[Endpoint]:
    """Main extraction pipeline: find all Gin endpoints and their call chains."""
    go_files = find_go_files(codebase_path)

    # Phase 1: Build function index across entire codebase
    all_functions: dict[str, FunctionDef] = {}
    file_contents: dict[str, str] = {}

    for fpath in go_files:
        content = Path(fpath).read_text(errors="replace")
        file_contents[fpath] = content
        funcs = extract_functions(fpath, content)
        all_functions.update(funcs)

    # Phase 2: Find all route registrations
    all_routes = []
    for fpath, content in file_contents.items():
        groups = extract_router_groups(content)
        routes = extract_routes(content, groups)
        for r in routes:
            r["source_file"] = fpath
        all_routes.extend(routes)

    # Phase 3: Resolve handlers and trace call chains
    endpoints = []
    for route in all_routes:
        handler_name = resolve_handler_name(route["handler"])
        handler_func = all_functions.get(handler_name)

        call_chain = trace_call_chain(handler_name, all_functions)
        call_chain_bodies = {}
        for fname in call_chain:
            if fname in all_functions:
                call_chain_bodies[fname] = all_functions[fname].body

        ep = Endpoint(
            method=route["method"],
            path=route["path"],
            handler_name=handler_name,
            handler_file=handler_func.file if handler_func else route["source_file"],
            handler_body=handler_func.body if handler_func else "<not found>",
            group_prefix=route["group_prefix"],
            call_chain=call_chain,
            call_chain_bodies=call_chain_bodies,
        )
        endpoints.append(ep)

    return endpoints


def format_endpoint_for_analysis(ep: Endpoint) -> str:
    """Format an endpoint and its call chain as a string for LLM analysis."""
    parts = [
        f"## Endpoint: {ep.method} {ep.full_path}",
        f"Handler: {ep.handler_name} (in {ep.handler_file})",
        "",
        "### Call Chain:",
        " -> ".join(ep.call_chain) if ep.call_chain else "(no traced calls)",
        "",
    ]
    for fname, body in ep.call_chain_bodies.items():
        parts.append(f"### Function: {fname}")
        parts.append(f"```go\n{body}\n```")
        parts.append("")
    return "\n".join(parts)
