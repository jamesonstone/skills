#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF' >&2
usage:
  worktree.sh path --branch <branch> [--repo-root <path>]
  worktree.sh create --branch <branch> --base <base-ref> [--repo-root <path>]
  worktree.sh remove --branch <branch> [--repo-root <path>]
EOF
  exit 1
}

if [[ $# -lt 1 ]]; then
  usage
fi

command="$1"
shift

repo_root="."
branch=""
base_ref=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      repo_root="$2"
      shift 2
      ;;
    --branch)
      branch="$2"
      shift 2
      ;;
    --base)
      base_ref="$2"
      shift 2
      ;;
    *)
      echo "unknown flag: $1" >&2
      usage
      ;;
  esac
done

if [[ -z "$branch" ]]; then
  echo "error: --branch is required" >&2
  usage
fi

repo_root="$(git -C "$repo_root" rev-parse --show-toplevel)"
repo_name="$(basename "$repo_root")"
safe_branch="$(printf '%s' "$branch" | sed 's#[^A-Za-z0-9._-]#-#g')"
worktree_root="$HOME/worktrees"
worktree_path="$worktree_root/${repo_name}-${safe_branch}"

case "$command" in
  path)
    printf '%s\n' "$worktree_path"
    ;;
  create)
    if [[ -z "$base_ref" ]]; then
      echo "error: --base is required for create" >&2
      usage
    fi
    mkdir -p "$worktree_root"
    if [[ -e "$worktree_path" ]]; then
      echo "error: worktree path already exists: $worktree_path" >&2
      exit 1
    fi
    if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$branch"; then
      git -C "$repo_root" worktree add "$worktree_path" "$branch"
    else
      git -C "$repo_root" worktree add -b "$branch" "$worktree_path" "$base_ref"
    fi
    printf '%s\n' "$worktree_path"
    ;;
  remove)
    if [[ ! -e "$worktree_path" ]]; then
      echo "error: worktree path does not exist: $worktree_path" >&2
      exit 1
    fi
    git -C "$repo_root" worktree remove "$worktree_path"
    git -C "$repo_root" worktree prune
    ;;
  *)
    echo "error: unknown command: $command" >&2
    usage
    ;;
esac
