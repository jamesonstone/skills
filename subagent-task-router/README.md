# Subagent Task Router

**Turn a pile of sequential tasks into a maximally parallel execution plan.**

The Subagent Task Router analyzes a set of coding tasks, researches which files and code areas each task touches, detects overlap, and produces an execution plan that groups overlapping tasks onto sequential lanes while letting independent tasks run in parallel via subagents.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Why It Exists](#why-it-exists)
3. [How It Works](#how-it-works)
4. [Quick Start](#quick-start)
5. [Using as a Skill](#using-as-a-skill)
6. [Detailed Workflow](#detailed-workflow)
7. [Key Concepts](#key-concepts)
8. [Examples](#examples)
9. [Troubleshooting](#troubleshooting)

---

## What It Does

Given a list of N coding tasks (each modifying different files), the router:

1. **Analyzes the blast radius** of each task (which files, packages, and interfaces it will touch)
2. **Detects overlaps** using file-level, package-level, and import-dependency analysis
3. **Builds an overlap graph** and partitions tasks into independent lanes
4. **Produces an execution plan** that maximizes parallel execution
5. **Routes lanes into git worktrees and agents** (or runs them sequentially when coupled)

**Input:** A `TASKS.md` file (or inline task list) with structured task details.
**Output:** An execution plan showing which tasks run in parallel and which run sequentially.

---

## Ideal Workflow

The ideal workflow uses a confirmation gate plus `git worktree` isolation:

1. Router analyzes `TASKS.md` and detects the execution lanes.
2. Router presents the plan and waits for explicit approval.
3. Router creates one branch per lane from the same base commit.
4. Router creates one worktree per lane at `~/worktrees/<repo>-<lane-branch>`.
5. Router spawns one agent per worktree.
6. Each agent executes its lane sequentially and commits locally.
7. User reviews each worktree.
8. Router recommends merge order.
9. Push and PR creation happen only if the user explicitly requests them.
10. Worktrees are cleaned up after review or explicit cleanup approval.

---

## Why It Exists

Running multiple coding tasks naively in parallel causes:

- **Merge conflicts** when two tasks touch the same file
- **Overwritten changes** when tasks compete for the same code area
- **Broken interfaces** when one task changes a function signature and another consumes it

The Subagent Task Router solves this by:

- **Avoiding conflicts** through precise overlap detection
- **Maximizing efficiency** by running truly independent tasks in parallel
- **Preserving correctness** through explicit tracing of imports and dependencies
- **Making plans portable** so they work with any coding agent (Claude Code, Cursor, Aider, manual execution)

---

## How It Works

The router runs through 5 phases:

### Phase 1: Locate and Parse Tasks

- Finds `TASKS.md` files in spec directories (`docs/specs/*/TASKS.md`)
- Parses task metadata: ID, title, status, dependencies, scope
- Filters to non-done tasks only
- Organizes tasks by feature (one feature at a time)

### Phase 2: Blast-Radius Research

- For each task, reads the SCOPE bullets and identifies keywords
- Searches the codebase for files containing those keywords
- Traces imports to find which other files depend on the modified interfaces
- Outputs a `blast_radius` object per task with files, packages, and importers

### Phase 3: Overlap Detection

- Builds an overlap graph: tasks are nodes, edges connect overlapping tasks
- Detects overlap when tasks share files, packages, or import dependencies
- Respects explicit DEPENDENCIES from TASKS.md
- Finds connected components (each becomes one "lane")

### Phase 4: Present Plan (Default)

- Outputs an execution plan showing lanes and task order
- Includes blast-radius evidence so the user can validate or override
- **Halts and waits for user confirmation** before dispatching any agents

### Phase 5: Dispatch (User-Confirmed)

- Only runs when the user explicitly approves the plan
- Creates one branch per lane from the same base commit
- Creates one worktree per lane at `~/worktrees/<repo>-<lane-branch>`
- Spawns one agent per lane with full task details and blast-radius info
- Agents execute their lane's tasks sequentially and commit locally
- Stops before push/PR unless the user explicitly asks for publish steps

---

## Quick Start

### 1. Prepare Your Tasks

Create a `TASKS.md` file in your spec directory:

```markdown
# Feature: Auth Refactor

| ID   | Title                    | Status | SCOPE                                                                              |
| ---- | ------------------------ | ------ | ---------------------------------------------------------------------------------- |
| T001 | Introduce JWT middleware | todo   | **pkg/middleware** - add new auth middleware, export JWTValidator function         |
| T002 | Update auth service      | todo   | **pkg/auth** - refactor identity.go to use new JWTValidator, update error handling |
| T003 | Add audit logging        | todo   | **pkg/audit** - new package, create audit logger, no existing imports              |

## T001: Introduce JWT middleware

**SCOPE:**

- New file `pkg/middleware/jwt.go`
- Exports `JWTValidator` function
- No existing imports yet

**ACCEPTANCE:**

- JWTValidator validates tokens correctly
- Middleware integrates with HTTP handler

---

## T002: Update auth service

**SCOPE:**

- Modify `pkg/auth/identity.go` to use `JWTValidator` from T001
- Update error messages to match audit logging (T003)

**ACCEPTANCE:**

- Auth service passes all existing tests
- Uses new JWT validation

---

## T003: Add audit logging

**SCOPE:**

- New package `pkg/audit`
- Create `logger.go` with audit event tracking
- No dependencies on other tasks

**ACCEPTANCE:**

- Audit logger compiles and runs
- Can be integrated later
```

### 2. Invoke the Router

Ask your agent (Claude Code, Cursor, or ChatGPT with Code Interpreter):

```
"Run the Subagent Task Router on my TASKS.md. Analyze the blast radius,
detect overlaps, and show me the execution plan."
```

Or manually run (requires Python 3.7+):

```bash
# 1. Generate blast radii for each task
python scripts/blast_radius.sh --root . --keywords "middleware,JWTValidator" --task-id T001

# 2. Combine radii and partition into lanes
python scripts/partition.py blast_radii.json

# 3. Review the plan and decide whether to dispatch
```

### 3. Review the Plan

The router outputs something like:

```
## Execution Plan — Auth Refactor

### Lane 1 (sequential)
  T001 → T002

**Reason:** Both touch pkg/middleware and pkg/auth; T002 imports JWTValidator from T001.

### Lane 2 (independent)
  T003

**Reason:** New pkg/audit package; no shared files or imports.

---

**Parallelism:** 2 lanes, 1 with depth 2 (sequential), 1 independent.

**Suggested branches:**
- lane-1-auth: T001 + T002
- lane-2-audit: T003

**Suggested worktree paths:**
- `~/worktrees/<repo>-lane-1-auth`
- `~/worktrees/<repo>-lane-2-audit`

Dispatch now, or adjust the plan?
```

### 4. Approve and Dispatch

If the plan looks good:

```
"Dispatch the plan. Route Lane 1 and Lane 2 to parallel agents."
```

The router then:

- Creates lane branches and worktrees
- Spins up agents for each lane worktree
- Each agent receives its task list + blast-radius files
- Tasks execute, minimizing merge conflicts
- Each lane commits locally and stops for review

---

## Using as a Skill

The router is a **VS Code Copilot Skill** defined in `SKILLS.md`.

### When to Trigger

Invoke when the user says:

- "Run my tasks"
- "Execute TASKS.md"
- "Parallelize these tasks"
- "Route tasks for parallel execution"
- "Spin up agents for my tasks"
- "Figure out what can run in parallel"
- Mentions a `TASKS.md` file in a spec directory

### How It Integrates

```yaml
name: subagent-task-router
trigger: ['run my tasks', 'route tasks', 'parallelize']
```

When triggered:

1. Search for `TASKS.md` in spec directories
2. Run Phase 1–3 (research, analyze, partition)
3. Present the plan to the user
4. Wait for confirmation before dispatching agents or creating worktrees

---

## Detailed Workflow

### Phase 1: Task Parsing

**Input:** `docs/specs/<feature>/TASKS.md`

The skill reads the task table and extracts:

- `task_id`: Unique identifier (e.g., `T001`)
- `title`: Short description
- `status`: `todo`, `in-progress`, or `done`
- `SCOPE`: Bullets describing what the task modifies
- `DEPENDENCIES`: Explicit ordering constraints (optional)

**Filtering:**

- Skip tasks with status `done`
- If all tasks are done, report success and stop
- If multiple features exist, ask user which one to route

**Output:** A list of pending tasks with metadata.

---

### Phase 2: Blast-Radius Research

For each task, determine its **blast radius**: the set of files and packages it will modify.

#### 2a. Keyword Extraction

From the SCOPE bullets, identify:

- Package names (e.g., `pkg/auth`)
- File names (e.g., `identity.go`)
- Function/type names (e.g., `JWTValidator`)
- Route paths (e.g., `/api/login`)
- Table names (e.g., `users`)
- Config keys (e.g., `jwt_secret`)

#### 2b. File Search

For each keyword:

```bash
# Search for the keyword in code
grep -rn "<keyword>" --include="*.go" --include="*.ts" --include="*.py" .

# Search for path matches
find . -path "*<keyword>*" -not -path "*/node_modules/*" -not -path "*/.git/*" -type f
```

Record every file path that would need modification.

#### 2c. Package Extraction

From each file path, derive its package/directory (coarser grain than files):

```
pkg/auth/identity.go     → pkg/auth
src/middleware/jwt.ts    → src/middleware
lib/audit/__init__.py    → lib/audit
```

#### 2d. Import Tracing (1-Level Deep)

For each modified file that exports a public interface:

```bash
# Go: find importers of a package
grep -rn '"project/pkg/auth"' --include="*.go" .

# TypeScript: find importers
grep -rn "from ['\"].*pkg/auth" --include="*.ts" .

# Python: find importers
grep -rn "from pkg.auth import\|import pkg.auth" --include="*.py" .
```

Record all files that directly import from the modified files (one level only, not transitive closure).

This catches cases where Task A changes a function signature and Task B consumes it.

#### Output: Blast Radius Object

```json
{
  "task_id": "T001",
  "files": ["pkg/middleware/jwt.go"],
  "packages": ["pkg/middleware"],
  "shared_resources": [],
  "importers": ["pkg/auth/identity.go"]
}
```

---

### Phase 3: Overlap Detection

#### 3a. Build Overlap Graph

Create a graph where:

- **Nodes** = tasks
- **Edges** = overlap conditions

#### 3b. Overlap Conditions

Two tasks overlap if:

1. They share ≥1 file in their blast radius
2. They touch different files in the **same package/directory**
3. They both modify the same test file
4. One task modifies a file imported by another task's files
5. Explicit `DEPENDENCIES` from TASKS.md

#### 3c. Partition into Lanes

Find connected components in the overlap graph:

- Each connected component = one **lane** (sequential execution)
- Lanes are independent and can run in parallel

#### 3d. Order Within Lanes

For each lane:

1. Respect explicit `DEPENDENCIES`
2. Use topological sort by file-level dependencies
3. Fall back to task ID order if ambiguous

**Output:**

```
Lane 1: [T001, T002]  (sequential, package overlap in pkg/auth)
Lane 2: [T003]        (independent)
Lane 3: [T004, T005]  (sequential, explicit dependency)
```

---

### Phase 4: Present Plan

Output the execution plan in human-readable format:

```markdown
## Execution Plan — <feature>

### Lane 1 (sequential)

T001 → T002

**Files:** pkg/middleware/jwt.go, pkg/auth/identity.go
**Reason:** T002 imports JWTValidator from T001 (Phase 2b)

### Lane 2 (independent)

T003

**Files:** pkg/audit/logger.go
**Reason:** New package, no imports or shared files

---

**Summary:**

- **Parallelism:** 2 lanes
- **Max depth:** 2 (Lane 1 sequential tasks)
- **Concurrency gain:** 1.5x speedup (2 lanes, avg depth 1.5)

**Suggested branches and worktrees:**

- `lane-1-middleware-auth` → `~/worktrees/<repo>-lane-1-middleware-auth`
- `lane-2-audit` → `~/worktrees/<repo>-lane-2-audit`

**Recommended merge order:**

- `lane-2-audit`
- `lane-1-middleware-auth`

**Next step:**
Approve the plan or adjust groupings. Once approved, each lane will be routed
to its own worktree and agent for parallel execution.
```

Include **blast-radius evidence** so the user can validate or override:

```markdown
## Blast-Radius Evidence

### T001

- **Files:** pkg/middleware/jwt.go
- **Packages:** pkg/middleware
- **Importers:** pkg/auth/identity.go (because it will import JWTValidator)

### T002

- **Files:** pkg/auth/identity.go
- **Packages:** pkg/auth
- **Importers:** pkg/bwell/connect_service.go (but T002 doesn't change the interface)

### T003

- **Files:** pkg/audit/logger.go
- **Packages:** pkg/audit
- **Importers:** (none yet, this is new)
```

---

### Phase 5: Dispatch

**Only proceed when the user confirms.**

#### For Subagent-Capable Runtimes

Create one branch and one worktree per lane, then spawn one agent per worktree:

```plaintext
Agent 1 (Lane 1):
  Worktree: ~/worktrees/<repo>-lane-1-auth-middleware
  Branch: lane-1-auth-middleware
  Task list: [T001, T002]
  Blast-radius files: [pkg/middleware/jwt.go, pkg/auth/identity.go, ...]
  Project context: (from AGENTS.md, CLAUDE.md, etc.)

Agent 2 (Lane 2):
  Worktree: ~/worktrees/<repo>-lane-2-audit
  Branch: lane-2-audit
  Task list: [T003]
  Blast-radius files: [pkg/audit/logger.go, ...]
  Project context: (same as above)
```

Each agent executes its tasks sequentially, commits locally, and reports results.
Pushes and PRs are explicit follow-up steps after review. If `gh` is unavailable
or the repo has no GitHub remote, stop at local commits and publish manually later.

#### For Manual Execution

Print worktree commands and instructions:

```bash
## Ready to Execute

### Lane 1 (Seq. Depth 2)
./scripts/worktree.sh create --repo-root . --branch lane-1-auth-middleware --base main
# cd ~/worktrees/<repo>-lane-1-auth-middleware
# Execute T001, then T002
# Details: see blast-radius evidence above

### Lane 2 (Seq. Depth 1)
./scripts/worktree.sh create --repo-root . --branch lane-2-audit --base main
# cd ~/worktrees/<repo>-lane-2-audit
# Execute T003
# Details: see blast-radius evidence above

After each lane completes, review the local commits, then push or open PRs only
if you want to publish them.
```

After review or publish, remove worktrees:

```bash
./scripts/worktree.sh remove --repo-root . --branch lane-1-auth-middleware
./scripts/worktree.sh remove --repo-root . --branch lane-2-audit
```

---

## Key Concepts

### Blast Radius

The set of files, packages, and import dependencies that a task will affect.

- **Direct:** Files explicitly mentioned in SCOPE
- **Indirect:** Files that import modified code (1-level deep)
- **Package-level:** All files in a shared package/directory

A large blast radius increases the chance of overlap with other tasks.

### Overlap Graph

A graph where:

- **Nodes** = tasks
- **Edges** = tasks that cannot run in parallel (they share files, packages, or imports)

Connected components in the overlap graph become execution lanes.

### Lane

A sequence of tasks that must run sequentially because they overlap.

- **Good:** Few long lanes with many short lanes (good parallelism)
- **Bad:** One long lane containing all tasks (no parallelism)

### Edge Case: Full Overlap

If all tasks land in one connected component, only one lane exists. No subagents are spawned — everything runs sequentially.

This is fine; it means the tasks are tightly coupled and cannot be parallelized.

### Edge Case: Zero Overlap

If no tasks share files, each task is its own lane. Maximum parallelism: N agents, all running in parallel.

---

## Examples

### Example 1: Independent Tasks

**Tasks:**

| ID   | Title       | SCOPE                            |
| ---- | ----------- | -------------------------------- |
| T001 | Add logging | pkg/logger: new file logger.go   |
| T002 | Add caching | pkg/cache: new file cache.go     |
| T003 | Add metrics | pkg/metrics: new file metrics.go |

**Analysis:**

- T001 creates `pkg/logger`, no imports → blast radius: [pkg/logger/logger.go]
- T002 creates `pkg/cache`, no imports → blast radius: [pkg/cache/cache.go]
- T003 creates `pkg/metrics`, no imports → blast radius: [pkg/metrics/metrics.go]
- No overlaps → 3 independent lanes

**Plan:**

```
Lane 1: T001 (parallel)
Lane 2: T002 (parallel)
Lane 3: T003 (parallel)

Result: 3x speedup (3 agents running simultaneously)
```

### Example 2: Sequential Tasks with Dependency

**Tasks:**

| ID   | Title             | SCOPE                                                    | Dependencies |
| ---- | ----------------- | -------------------------------------------------------- | ------------ |
| T001 | Create interface  | pkg/auth: new file auth.go, export Validator interface   | —            |
| T002 | Implement service | pkg/auth: auth_service.go imports Validator from auth.go | T001         |
| T003 | Add tests         | pkg/auth: test everything in pkg/auth                    | T001, T002   |

**Analysis:**

- T001 blast radius: [pkg/auth/auth.go]
- T002 blast radius: [pkg/auth/auth_service.go], importers: [T001 output]
- T003 blast radius: [pkg/auth/auth_test.go], importers: [T001, T002 output]
- All in same package → overlap → 1 lane

**Plan:**

```
Lane 1: T001 → T002 → T003 (sequential)

Result: 1x speedup (sequential execution, but correct ordering)
```

### Example 3: Mixed Tasks (Some Parallel, Some Sequential)

**Tasks:**

| ID   | Title           | SCOPE                                      |
| ---- | --------------- | ------------------------------------------ |
| T001 | Auth middleware | pkg/middleware/auth.go                     |
| T002 | Error handling  | pkg/apierror/errors.go                     |
| T003 | Use middleware  | pkg/api/handler.go imports auth middleware |
| T004 | Use errors      | pkg/api/handler.go imports error types     |

**Analysis:**

- T001 creates middleware → importers: [pkg/api/handler.go]
- T002 creates error types → importers: [pkg/api/handler.go]
- T003 and T004 both modify pkg/api/handler.go → overlap
- T001 and T003 overlap via imports
- T002 and T004 overlap via imports

**Lanes:**

```
Lane 1: T001 → T003 (sequential, shared import chain)
Lane 2: T002 → T004 (sequential, shared import chain)

Result: 1.5x theoretical speedup (2 lanes, depth ~2 each)
```

---

## Troubleshooting

### Problem: All Tasks in One Lane (No Parallelism)

**Cause:** Tasks share packages, files, or imports. This is often correct (they're tightly coupled).

**Check:**

1. Review the blast-radius evidence in the plan
2. Verify that the overlaps are real (not false positives from grep)
3. If overlap is a mistake, adjust the SCOPE bullets to be more precise

**Fix Options:**

- Reorder tasks to minimize rework (Phase 3d)
- Split tasks into smaller, more independent pieces
- Accept sequential execution if coupling is unavoidable

### Problem: Too Many Lanes, Low Utilization

**Cause:** Tasks are too small or poorly scoped. Many lanes with 1–2 tasks each and low depth.

**Example:**

```
Lane 1: T001 (depth 1)
Lane 2: T002 (depth 1)
Lane 3: T003 (depth 1)
...
Lane 50: T050 (depth 1)
```

**Fix:**

- Merge related tasks in the TASKS.md file
- Reduce the number of tasks by grouping work
- Accept that many small tasks will have good parallelism but high overhead

### Problem: Unexpected Overlap (False Positive)

**Cause:** Grep found a keyword in a comment or unrelated code.

**Example:**

```
Blast radius for "auth" includes every file with a comment mentioning authentication.
```

**Fix:**

1. Review the grep results in the blast-radius evidence
2. Refine the keyword search (use more specific terms, exclude comments)
3. Use `--additional-keywords` flag to be more selective
4. Manually override the blast radius in the plan

### Problem: Missing Overlap (False Negative)

**Cause:** A task modifies code that another task imports, but the import isn't detected.

**Example:**

```
T001 creates a function in pkg/auth/new_func.go
T002 should import it, but the import traces didn't find it.
```

**Fix:**

1. Check that the modified function is actually **exported** (public)
2. Verify import statements in T002 match the package path
3. Add explicit `DEPENDENCIES: [T001]` in TASKS.md to force ordering
4. Run `trace_imports.py` manually to debug

### Problem: Script Errors (Python/Bash Issues)

**Cause:** Missing dependencies, permission issues, or syntax errors.

**Debug:**

```bash
# Check Python version
python --version  # should be 3.7+

# Check script permissions
chmod +x scripts/*.sh scripts/*.py

# Run with verbose output
python scripts/partition.py blast_radii.json --verbose
```

---

## Summary

The Subagent Task Router transforms a todo list of coding tasks into a maximally parallel execution plan by:

1. **Analyzing** which code areas each task touches (blast radius)
2. **Detecting** overlaps using file, package, and import-level analysis
3. **Partitioning** tasks into independent lanes
4. **Planning** parallel execution while respecting dependencies
5. **Dispatching** lanes to worktrees and agents (or manual execution)
6. **Stopping at local commits** so review happens before push/PR

**Use it when:**

- You have multiple coding tasks and want to run them in parallel
- You need to avoid merge conflicts and maintain code correctness
- You want a detailed blast-radius analysis for code review

**Next steps:**

- Create a `TASKS.md` file with your tasks
- Invoke the router
- Review the execution plan
- Approve worktree creation and dispatch
- Review local lane commits before any publish step
