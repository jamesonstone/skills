#!/usr/bin/env python3
"""
partition.py — overlap graph partitioner for subagent-task-router

Input:  JSON file with blast_radius objects + optional explicit dependencies
Output: JSON lane assignments to stdout

Usage:
  python partition.py blast_radii.json
  python partition.py blast_radii.json --deps '{"T002":["T001"],"T004":["T001","T003"]}'

Input format (blast_radii.json):
[
  {
    "task_id": "T001",
    "files": ["pkg/auth/identity.go", "pkg/apierror/errors.go"],
    "packages": ["pkg/auth", "pkg/apierror"],
    "shared_resources": ["quinn identity"],
    "importers": ["pkg/bwell/connect_service.go"]
  },
  ...
]
"""

import json
import sys
from collections import defaultdict, deque
from pathlib import Path


def extract_package(filepath: str) -> str:
    """extract parent directory as package identifier"""
    return str(Path(filepath).parent)


def build_overlap_graph(blast_radii: list, deps: dict) -> dict:
    """build adjacency list from overlap conditions and explicit deps"""
    task_ids = [br["task_id"] for br in blast_radii]
    adj = defaultdict(set)

    # index: task_id -> set of files, packages, importers
    file_index = {}
    pkg_index = {}
    all_files_index = {}

    for br in blast_radii:
        tid = br["task_id"]
        files = set(br.get("files", []))
        importers = set(br.get("importers", []))
        all_files = files | importers
        pkgs = set(br.get("packages", []))
        # also derive packages from file paths
        for f in all_files:
            pkgs.add(extract_package(f))

        file_index[tid] = files
        pkg_index[tid] = pkgs
        all_files_index[tid] = all_files

    # pairwise overlap detection
    task_list = list(file_index.keys())
    for i in range(len(task_list)):
        for j in range(i + 1, len(task_list)):
            a, b = task_list[i], task_list[j]

            # file-level overlap (including importers)
            if all_files_index[a] & all_files_index[b]:
                adj[a].add(b)
                adj[b].add(a)
                continue

            # package-level overlap (conservative)
            if pkg_index[a] & pkg_index[b]:
                adj[a].add(b)
                adj[b].add(a)
                continue

            # cross-check: a's importers in b's files or vice versa
            a_importers = set(blast_radii[i].get("importers", []))
            b_importers = set(blast_radii[j].get("importers", []))
            if (a_importers & file_index[b]) or (b_importers & file_index[a]):
                adj[a].add(b)
                adj[b].add(a)
                continue

    # explicit dependencies add edges
    for tid, dep_list in deps.items():
        for dep in dep_list:
            if dep in file_index and tid in file_index:
                adj[tid].add(dep)
                adj[dep].add(tid)

    return adj


def find_connected_components(task_ids: list, adj: dict) -> list:
    """BFS connected components"""
    visited = set()
    components = []

    for tid in task_ids:
        if tid in visited:
            continue
        component = []
        queue = deque([tid])
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(component)

    return components


def order_within_lane(component: list, deps: dict) -> list:
    """topological sort respecting explicit deps, fallback to ID order"""
    component_set = set(component)
    in_degree = defaultdict(int)
    local_adj = defaultdict(list)

    for tid in component:
        for dep in deps.get(tid, []):
            if dep in component_set:
                local_adj[dep].append(tid)
                in_degree[tid] += 1

    # kahn's algorithm
    queue = deque(sorted([t for t in component if in_degree[t] == 0]))
    result = []
    while queue:
        node = queue.popleft()
        result.append(node)
        for neighbor in local_adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # if cycle or missing nodes, append remainder in ID order
    remaining = sorted(set(component) - set(result))
    result.extend(remaining)

    return result


def partition(blast_radii: list, deps: dict = None) -> dict:
    """main entry point — returns lane assignments"""
    if deps is None:
        deps = {}

    task_ids = [br["task_id"] for br in blast_radii]
    adj = build_overlap_graph(blast_radii, deps)
    components = find_connected_components(task_ids, adj)

    lanes = []
    for i, component in enumerate(components):
        ordered = order_within_lane(component, deps)
        # collect packages for lane label
        pkgs = set()
        for br in blast_radii:
            if br["task_id"] in set(ordered):
                pkgs.update(br.get("packages", []))
        lanes.append({
            "lane": i + 1,
            "tasks": ordered,
            "packages": sorted(pkgs),
            "sequential_depth": len(ordered),
        })

    # collect overlap evidence
    overlaps = []
    for a in adj:
        for b in adj[a]:
            pair = tuple(sorted([a, b]))
            if pair not in overlaps:
                overlaps.append(pair)

    return {
        "total_lanes": len(lanes),
        "max_parallelism": len(lanes),
        "lanes": lanes,
        "overlap_edges": [list(p) for p in overlaps],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: partition.py <blast_radii.json> [--deps '<json>']", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1]) as f:
        blast_radii = json.load(f)

    deps = {}
    if "--deps" in sys.argv:
        idx = sys.argv.index("--deps")
        deps = json.loads(sys.argv[idx + 1])

    result = partition(blast_radii, deps)
    print(json.dumps(result, indent=2))
