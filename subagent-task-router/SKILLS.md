---
name: subagent-task-router
description: >
  Analyze a set of coding tasks (from a TASKS.md file or user-provided list),
  research which files and code areas each task touches, detect overlaps, and
  produce a maximally parallel execution plan that groups overlapping tasks
  onto the same sequential lane while letting independent tasks run in parallel
  via subagents. Use this skill whenever the user says "run my tasks",
  "execute TASKS.md", "parallelize these tasks", "route tasks", "spin up
  agents for my tasks", mentions a TASKS.md file in a spec directory, or asks
  to break work into parallel lanes. Also trigger when the user asks to
  "figure out what can run in parallel" or wants to "maximize parallelism"
  across a set of code changes.
---

# Subagent Task Router

Route a set of coding tasks into maximally parallel execution lanes by
analyzing codebase overlap, then dispatch each lane to an agent (or run
sequentially when full overlap is detected).

Works with any coding agent that can access the filesystem: Claude Code,
Codex, Cursor, Aider, or manual execution.

## Overview

Given N tasks that each modify some subset of a codebase, naively running
them in parallel causes merge conflicts and overwritten changes. This skill
researches the blast radius of each task, builds an overlap graph, partitions
into independent groups, and runs each group on its own agent.

**Default mode is plan-only.** The skill outputs the execution plan and waits
for user confirmation before dispatching any agents. This makes the plan
portable — the user can hand it to Codex, Claude Code, or execute manually.

## Workflow

### Phase 1 — Locate and Parse Tasks

1. Search for `TASKS.md` files at `./docs/specs/*/TASKS.md`.
2. **If multiple features exist, ask the user which feature to route.**
   Operate on one feature at a time — never aggregate across features.
3. If no file exists, accept an inline task list from the user.
4. Parse the progress table and task details. Extract for each task:
   - ID, title, status, dependencies
   - SCOPE bullets (the primary signal for blast-radius analysis)
   - ACCEPTANCE criteria
5. Filter to non-done tasks only (skip tasks with status `done`). If all tasks
   are done, tell the user and stop.

### Phase 2 — Blast-Radius Research

This is the most important phase. For each task, determine which files and
packages it will likely modify.

**Research steps per task:**

```plaintext
1. Read the task's SCOPE bullets carefully.
2. Identify keywords: package names, file names, function names, route paths,
   table names, config keys.
3. For each keyword, search the codebase:
   - `grep -rn "<keyword>" --include="*.go" --include="*.ts" --include="*.py" .`
   - `find . -path "*/keyword*" -not -path "*/node_modules/*" -not -path "*/.git/*"`
4. Record every file path that would need modification.
5. Also record the *package/directory* each file belongs to (coarser grain).
6. For each file in the blast radius that exports a public interface,
   trace one level of importers (see Phase 2b).
```

**Output per task:** a `blast_radius` object:

```json
{
  "task_id": "T003",
  "files": ["pkg/records/repository.go", "pkg/records/models.go"],
  "packages": ["pkg/records"],
  "shared_resources": ["records table", "storage_key column"],
  "importers": ["pkg/bwell/connect_service.go"]
}
```

Spend real effort here. Grep, read files, trace imports. A wrong blast radius
produces a wrong partition — either unnecessary serialization (too conservative)
or file conflicts (too aggressive).

#### Phase 2b — 1-Level Import Tracing

After identifying each task's directly modified files, check whether any of
those files export public interfaces (exported functions, types, structs,
classes, or module exports). If so, find files that import them — one level
deep only, not the full transitive closure.

**How to trace:**

```plaintext
# go: find importers of a package
grep -rn '"project/pkg/auth"' --include="*.go" .

# typescript: find importers of a module
grep -rn "from ['\"].*pkg/auth" --include="*.ts" --include="*.tsx" .

# python: find importers of a module
grep -rn "from pkg.auth import\|import pkg.auth" --include="*.py" .
```

If another task's blast radius includes any of these importer files, the two
tasks are coupled even though they don't directly share files. Add an overlap
edge between them.

This catches the common case where Task A changes an interface signature and
Task B consumes that interface — even when Task B's SCOPE doesn't mention
the changed file by name.

Do NOT trace beyond one level. Full transitive closure is too expensive and
produces overly conservative groupings.

### Phase 3 — Overlap Detection and Partitioning

Build an overlap graph where tasks are nodes and edges connect tasks that
overlap.

**What counts as overlap (all of these force serialization):**

- Two tasks share ≥1 file in their blast radius
- Two tasks touch different files in the **same package/directory**
- Two tasks both modify the same test file (even if append-only)
- One task modifies a file that exports a public interface imported by a
  file in another task's blast radius (detected in Phase 2b)
- Explicit DEPENDENCIES from TASKS.md

**Algorithm:**

1. Start with explicit DEPENDENCIES — these force ordering.
2. Add edges for every overlap condition above.
3. Find connected components in the resulting graph.
4. Each connected component becomes one **lane** (sequential execution).
5. Lanes are independent and run in parallel.

**Ordering within a lane:**

- Respect explicit dependency order from TASKS.md.
- When no explicit order exists, use topological sort by file-level
  dependencies (e.g., if T003 creates a function that T004 calls, T003
  goes first).
- If still ambiguous, use the original task ID order.

**Edge case — full overlap:**
If all tasks land in one connected component, emit a single lane. No
subagents. Tell the user: "All tasks overlap — running sequentially on a
single agent."

**Edge case — zero overlap:**
If no tasks share files, each task is its own lane. Maximum parallelism.

### Phase 4 — Present the Execution Plan (default output)

The skill defaults to **plan-only mode**. Output the plan and stop. The user
decides whether to dispatch, hand off to another agent, or adjust groupings.

```plaintext
## Execution Plan — <feature-name>

### Lane 1 (parallel)  — pkg/auth, pkg/middleware
  T001 → T002 (sequential: shared pkg/auth/identity.go)

### Lane 2 (parallel)  — pkg/records
  T003 → T005 (sequential: shared pkg/records/repository.go)

### Lane 3 (parallel)  — pkg/bwell
  T004 (independent)

Parallelism: 3 lanes, max 2 sequential depth

### Blast-Radius Evidence
T001: [files...] + importers: [files...]
T002: [files...]
...

### Suggested Branch Names (for branch-based dispatch)
lane-1/auth-middleware
lane-2/records
lane-3/bwell
```

Include the blast-radius evidence so the user can override grouping.
Ask: "Dispatch these lanes now, or adjust the plan?"

### Phase 5 — Dispatch (on user confirmation only)

Only proceed when the user explicitly confirms.

**Subagent-capable runtimes (Claude Code, Cowork):**

- Spawn one agent per lane.
- Each agent receives:
  - The ordered list of tasks for its lane
  - The full task details (scope, acceptance)
  - The blast-radius file list (so it knows where to focus)
  - Project context from `AGENTS.md`, `CLAUDE.md`, `CODEX.md`, or equivalent
- Agents execute tasks sequentially within their lane.

**Single-agent runtimes (Claude.ai, no subagent support):**

- Execute lanes sequentially (lane 1 → lane 2 → …).
- Within each lane, execute tasks in order.
- Inform the user: "No subagent support — running lanes sequentially."

**Branch-based parallelism (Codex, GitHub Actions):**

- Each lane operates on its own branch forked from the same base commit.
- The execution plan includes suggested branch names.
- After all lanes complete, the user merges branches. Lanes are conflict-free
  by construction if the blast-radius research was accurate.

**Error handling:** If a lane fails mid-execution, other running lanes
continue. Failures are collected and reported in Phase 6. Do not halt
healthy lanes because of a failure in an independent lane.

### Phase 6 — Collect, Report, and Update TASKS.md

After all lanes complete:

1. **Report results** per task: pass/fail, files modified, acceptance met.
2. **Flag drift** — any file modifications outside the predicted blast radius.
3. **Update TASKS.md:**
   - Set `STATUS` to `done` for completed tasks.
   - Add evidence notes to the task's ACCEPTANCE section (e.g., files
     modified, test output, verification commands run).
   - For failed tasks, set `STATUS` to `failed` and add error context.
4. If any task failed, report the failure and suggest next steps.

The TASKS.md update ensures the file remains the single source of truth for
feature progress. Agents should never leave TASKS.md stale after execution.

## Important Principles

- **Research over guessing.** Never assume blast radius — always grep and read.
  A 5-minute research phase prevents hours of conflict resolution.
- **Conservative overlap is safer.** When uncertain whether two tasks touch
  the same file, put them in the same lane. False serialization wastes time;
  false parallelism corrupts code.
- **Same package = same lane.** Two tasks touching different files in the same
  package are always serialized. Package-level refactors are common and
  file-level analysis misses them.
- **Test files are real overlap.** Two tasks adding tests to the same test
  file must serialize, even when the additions are append-only. Merge
  conflicts in test files are subtle and easy to miss.
- **Trace imports one level deep.** If a task changes a public interface,
  find its direct importers and check for overlap with other tasks' blast
  radii. Do not trace the full transitive closure — one level catches the
  common case without over-serializing.
- **Respect existing dependency declarations.** TASKS.md dependencies are
  explicit ordering constraints that override the overlap analysis.
- **Generated files are shared.** Swagger/OpenAPI docs, migration files, lock
  files — treat these as shared by all tasks that trigger regeneration.
- **Agents can't cross filesystem boundaries.** Codex and similar sandboxed
  agents operate in isolated checkouts. Never assume one agent can read
  another agent's working tree.
- **Lanes are fault-isolated.** A failure in one lane does not halt others.
  Independent lanes continue; failures are reported at the end.

## Agent Prompt Template

When dispatching to an agent, use this structure. Adapt the framing to the
target runtime (e.g., Codex tasks are typically shorter and more prescriptive).

```plaintext
You are executing a lane of coding tasks sequentially.

## Project Context
<contents of AGENTS.md, CLAUDE.md, CODEX.md, or equivalent — whichever exists>

## Your Tasks (execute in order)

### Task 1: <title>
- SCOPE: <scope bullets>
- ACCEPTANCE: <acceptance bullets>
- FILES TO MODIFY: <blast radius file list>

### Task 2: <title>
...

## Rules
- Complete each task fully before starting the next.
- Do not modify files outside your assigned blast radius unless
  strictly necessary — if you must, note it in your completion report.
- Run tests after each task if a test command is available.
- After completing all tasks, update TASKS.md: set status to done and
  add evidence notes under each task's ACCEPTANCE section.
- Report: for each task, list files modified and whether acceptance
  criteria are met.
```

## Project Context File Resolution

The skill looks for project context in this order:

1. `AGENTS.md` — agent-agnostic project instructions (preferred)
2. `CLAUDE.md` — Claude Code conventions
3. `CODEX.md` — Codex conventions
4. `CONSTITUTION.md` — project principles / constraints
5. `README.md` — fallback general context

Use the first file found. If multiple exist, merge relevant sections
(e.g., `AGENTS.md` for workflow + `CONSTITUTION.md` for constraints).

## Bundled Scripts

Three scripts automate the most error-prone steps. The agent executing this
skill should call these instead of reasoning through the steps manually.

### `scripts/blast_radius.sh`

Wraps the grep + find pattern from Phase 2 into a repeatable invocation.

```bash
./scripts/blast_radius.sh \
  --root . \
  --keywords "repository,records,upsert" \
  --extensions ".go,.ts,.py" \
  --task-id T003
```

Output: JSON blast_radius object. The `shared_resources` and `importers`
fields are empty — fill `importers` by running `trace_imports.py` on each
file that exports a public interface.

### `scripts/trace_imports.py`

1-level import tracer. Supports Go, TypeScript/JS, and Python.

```bash
python scripts/trace_imports.py pkg/auth/identity.go --root .
# output: ["pkg/records/service.go", "pkg/bwell/connect_service.go"]
```

Run this on every file in a task's blast radius that exports public
symbols. Add the results to the `importers` field of the blast_radius
object before feeding it to `partition.py`.

### `scripts/partition.py`

Takes a JSON array of blast_radius objects, builds the overlap graph,
computes connected components via BFS, and outputs lane assignments.

```bash
python scripts/partition.py blast_radii.json \
  --deps '{"T002":["T001"],"T004":["T001","T003"]}'
```

Output: JSON with `lanes`, `overlap_edges`, `total_lanes`, and
`max_parallelism`. This replaces all manual graph reasoning in Phase 3.

### Recommended workflow

```plaintext
1. For each task, run blast_radius.sh → get files + packages
2. For each file with public exports, run trace_imports.py → fill importers
3. Collect all blast_radius objects into one JSON array
4. Run partition.py with explicit deps → get lane assignments
5. Present the plan (Phase 4)
```

## Reference: TASKS.md Format

The expected TASKS.md format contains:

- A **progress table** with columns: ID, TASK, STATUS, OWNER, DEPENDENCIES
- A **task list** with markdown checkboxes
- **Task details** sections with GOAL, SCOPE, and ACCEPTANCE
- A **dependencies** section
- Optional **notes** and **plan links**

The skill handles variations gracefully — if a field is missing, skip it.
If the format is completely different, ask the user to clarify task boundaries.
