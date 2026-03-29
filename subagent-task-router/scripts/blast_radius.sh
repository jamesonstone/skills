#!/usr/bin/env bash
# blast_radius.sh — find files matching keywords in a codebase
#
# Usage:
#   ./blast_radius.sh --root <project_root> --keywords "keyword1,keyword2,..."
#                     [--extensions ".go,.ts,.py"] [--task-id T001]
#
# Output: JSON blast_radius object to stdout

set -euo pipefail

ROOT="."
KEYWORDS=""
EXTENSIONS=".go,.ts,.tsx,.py,.js,.jsx"
TASK_ID="unknown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="$2"; shift 2 ;;
    --keywords) KEYWORDS="$2"; shift 2 ;;
    --extensions) EXTENSIONS="$2"; shift 2 ;;
    --task-id) TASK_ID="$2"; shift 2 ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$KEYWORDS" ]]; then
  echo "error: --keywords required" >&2
  echo "usage: blast_radius.sh --root . --keywords 'repository,records,upsert' [--task-id T001]" >&2
  exit 1
fi

# build grep --include flags
INCLUDE_FLAGS=""
IFS=',' read -ra EXT_ARRAY <<< "$EXTENSIONS"
for ext in "${EXT_ARRAY[@]}"; do
  INCLUDE_FLAGS="$INCLUDE_FLAGS --include=*${ext}"
done

# collect matching files across all keywords
TMPFILE=$(mktemp)
trap 'rm -f $TMPFILE' EXIT

IFS=',' read -ra KW_ARRAY <<< "$KEYWORDS"
for kw in "${KW_ARRAY[@]}"; do
  kw=$(echo "$kw" | xargs) # trim whitespace
  # grep for keyword
  grep -rln "$kw" "$INCLUDE_FLAGS" \
    --exclude-dir=node_modules \
    --exclude-dir=.git \
    --exclude-dir=vendor \
    --exclude-dir=__pycache__ \
    --exclude-dir=dist \
    "$ROOT" 2>/dev/null >> "$TMPFILE" || true

  # find for path matches
  find "$ROOT" -path "*${kw}*" \
    -not -path "*/node_modules/*" \
    -not -path "*/.git/*" \
    -not -path "*/vendor/*" \
    -not -path "*/__pycache__/*" \
    -type f 2>/dev/null >> "$TMPFILE" || true
done

# deduplicate and sort
FILES=$(sort -u "$TMPFILE")

# extract unique packages (parent directories)
PACKAGES=$(echo "$FILES" | while IFS= read -r f; do
  [[ -n "$f" ]] && dirname "$f"
done | sort -u)

# output JSON
echo "{"
echo "  \"task_id\": \"$TASK_ID\","

# files array
echo "  \"files\": ["
FIRST=true
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  if $FIRST; then FIRST=false; else echo ","; fi
  printf "    \"%s\"" "$f"
done <<< "$FILES"
echo ""
echo "  ],"

# packages array
echo "  \"packages\": ["
FIRST=true
while IFS= read -r p; do
  [[ -z "$p" ]] && continue
  if $FIRST; then FIRST=false; else echo ","; fi
  printf "    \"%s\"" "$p"
done <<< "$PACKAGES"
echo ""
echo "  ],"

echo "  \"shared_resources\": [],"
echo "  \"importers\": []"
echo "}"
