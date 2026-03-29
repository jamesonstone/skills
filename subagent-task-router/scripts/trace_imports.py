#!/usr/bin/env python3
"""
trace_imports.py — 1-level import tracer for subagent-task-router

Finds all files that directly import a given module/package.
Supports Go, TypeScript/JavaScript, and Python.

Usage:
  python trace_imports.py <file_path> --root <project_root> [--lang go|ts|py]

Output: JSON list of importer file paths to stdout.

Examples:
  python trace_imports.py pkg/auth/identity.go --root .
  python trace_imports.py src/lib/auth.ts --root . --lang ts
  python trace_imports.py pkg/auth/__init__.py --root . --lang py
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def detect_language(filepath: str) -> str:
    """infer language from file extension"""
    ext = Path(filepath).suffix.lower()
    lang_map = {
        ".go": "go",
        ".ts": "ts", ".tsx": "ts", ".js": "ts", ".jsx": "ts",
        ".mjs": "ts", ".mts": "ts",
        ".py": "py",
    }
    return lang_map.get(ext, "")


def go_import_path(filepath: str, root: str) -> str:
    """derive Go import path from file path
    e.g., pkg/auth/identity.go -> the package is pkg/auth
    Go imports reference packages, not files"""
    return str(Path(filepath).parent)


def grep_files(pattern: str, root: str, extensions: list) -> list:
    """run grep and return matching file paths"""
    include_args = []
    for ext in extensions:
        include_args.extend(["--include", f"*{ext}"])

    cmd = [
        "grep", "-rln", pattern,
        *include_args,
        "--exclude-dir=node_modules",
        "--exclude-dir=.git",
        "--exclude-dir=vendor",
        "--exclude-dir=__pycache__",
        "--exclude-dir=dist",
        root,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def trace_go(filepath: str, root: str) -> list:
    """find Go files that import the package containing filepath"""
    pkg_path = go_import_path(filepath, root)

    # try to find the module path from go.mod
    go_mod = os.path.join(root, "go.mod")
    module_prefix = ""
    if os.path.exists(go_mod):
        with open(go_mod) as f:
            for line in f:
                if line.startswith("module "):
                    module_prefix = line.split()[1].strip()
                    break

    # build possible import strings
    patterns = [pkg_path]
    if module_prefix:
        patterns.append(f"{module_prefix}/{pkg_path}")

    results = set()
    for pattern in patterns:
        # escape dots for grep
        escaped = pattern.replace(".", r"\.")
        matches = grep_files(f'".*{escaped}"', root, [".go"])
        results.update(matches)

    # exclude the file itself and files in the same package
    source_pkg = str(Path(filepath).parent)
    results = {
        f for f in results
        if not f.endswith(filepath) and str(Path(f).parent) != source_pkg
    }

    return sorted(results)


def trace_ts(filepath: str, root: str) -> list:
    """find TS/JS files that import from the module at filepath"""
    p = Path(filepath)
    stem = p.stem
    # strip index — import from directory resolves to index
    if stem == "index":
        module_name = str(p.parent)
    else:
        module_name = str(p.parent / stem)

    # normalize separators
    module_name = module_name.replace("\\", "/")

    # build patterns: relative imports, alias imports, bare specifiers
    patterns = [module_name]
    # also try just the final component for aliased imports (e.g., @/lib/auth)
    parts = module_name.split("/")
    if len(parts) >= 2:
        patterns.append("/".join(parts[-2:]))

    results = set()
    for pattern in patterns:
        escaped = pattern.replace(".", r"\.")
        # match from '...' or from "..."
        matches = grep_files(f"from.*['\"].*{escaped}", root, [".ts", ".tsx", ".js", ".jsx", ".mjs", ".mts"])
        results.update(matches)
        # also match require('...')
        matches = grep_files(f"require.*['\"].*{escaped}", root, [".ts", ".tsx", ".js", ".jsx"])
        results.update(matches)

    # exclude self
    results = {f for f in results if not f.endswith(filepath)}
    return sorted(results)


def trace_py(filepath: str, root: str) -> list:
    """find Python files that import the module at filepath"""
    p = Path(filepath)
    # convert path to dotted module name
    if p.stem == "__init__":
        module_parts = list(p.parent.parts)
    else:
        module_parts = list(p.parent.parts) + [p.stem]

    # strip root prefix if present
    root_parts = Path(root).parts
    if module_parts[:len(root_parts)] == list(root_parts):
        module_parts = module_parts[len(root_parts):]

    dotted = ".".join(module_parts)
    # also try partial (last 2 components)
    partial = ".".join(module_parts[-2:]) if len(module_parts) >= 2 else dotted

    results = set()
    for pattern in [dotted, partial]:
        escaped = pattern.replace(".", r"\.")
        matches = grep_files(f"(from|import).*{escaped}", root, [".py"])
        results.update(matches)

    # exclude self
    results = {f for f in results if not f.endswith(filepath)}
    return sorted(results)


TRACERS = {
    "go": trace_go,
    "ts": trace_ts,
    "py": trace_py,
}


def trace_imports(filepath: str, root: str = ".", lang: str = "") -> list:
    """main entry point"""
    if not lang:
        lang = detect_language(filepath)
    if not lang:
        return []

    tracer = TRACERS.get(lang)
    if not tracer:
        return []

    return tracer(filepath, root)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Trace 1-level importers of a file")
    parser.add_argument("filepath", help="File to trace importers for")
    parser.add_argument("--root", default=".", help="Project root directory")
    parser.add_argument("--lang", default="", choices=["go", "ts", "py", ""],
                        help="Language override (auto-detected from extension)")
    args = parser.parse_args()

    importers = trace_imports(args.filepath, args.root, args.lang)
    print(json.dumps(importers, indent=2))
