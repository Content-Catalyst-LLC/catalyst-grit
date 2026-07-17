#!/usr/bin/env bash
set -euo pipefail

PRODUCT="Catalyst Grit"
VERSION="1.0.1"
RELEASE_NAME="Repository Integrity and Product Consolidation"
ARCHIVE_NAME="catalyst-grit-v${VERSION}-repository.zip"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

say() { printf '\n==> %s\n' "$1"; }
fail() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

find_archive() {
  local candidate
  for candidate in \
    "$SCRIPT_DIR/$ARCHIVE_NAME" \
    "$PWD/$ARCHIVE_NAME" \
    "$HOME/Downloads/$ARCHIVE_NAME"; do
    if [ -f "$candidate" ]; then printf '%s\n' "$candidate"; return 0; fi
  done
  return 1
}

looks_like_repo() {
  [ -d "$1/.git" ] && [ -f "$1/catalyst_grit_manifest.json" ]
}

find_repo() {
  local candidate remote
  if [ -n "${CATALYST_GRIT_REPO:-}" ] && looks_like_repo "$CATALYST_GRIT_REPO"; then
    printf '%s\n' "$CATALYST_GRIT_REPO"; return 0
  fi
  if looks_like_repo "$PWD"; then printf '%s\n' "$PWD"; return 0; fi
  for candidate in \
    "$HOME/Downloads/catalyst-grit" \
    "$HOME/catalyst-grit" \
    "$SCRIPT_DIR/catalyst-grit" \
    "$(dirname "$SCRIPT_DIR")/catalyst-grit"; do
    if looks_like_repo "$candidate"; then printf '%s\n' "$candidate"; return 0; fi
  done
  for candidate in "$HOME/Downloads"/catalyst-grit*; do
    if [ -d "$candidate/.git" ]; then
      remote="$(git -C "$candidate" remote get-url origin 2>/dev/null || true)"
      case "$remote" in *Content-Catalyst-LLC/catalyst-grit*) printf '%s\n' "$candidate"; return 0;; esac
    fi
  done
  return 1
}

say "$PRODUCT v$VERSION installer"
ARCHIVE="$(find_archive || true)"
[ -n "$ARCHIVE" ] || fail "Could not find $ARCHIVE_NAME beside this script, in the current directory, or in Downloads."
REPO="$(find_repo || true)"
[ -n "$REPO" ] || fail "Could not locate the catalyst-grit Git repository. Set CATALYST_GRIT_REPO=/path/to/repository and rerun."

printf 'Release archive: %s\n' "$ARCHIVE"
printf 'Git repository: %s\n' "$REPO"
printf 'Remote: %s\n' "$(git -C "$REPO" remote get-url origin 2>/dev/null || echo '(none)')"

TMP="$(mktemp -d "${TMPDIR:-/tmp}/catalyst-grit-v101.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
unzip -q "$ARCHIVE" -d "$TMP"
SOURCE="$TMP/catalyst-grit-v$VERSION"
[ -f "$SOURCE/VERSION" ] || fail "Release source is missing VERSION."
[ "$(tr -d '[:space:]' < "$SOURCE/VERSION")" = "$VERSION" ] || fail "Release archive version mismatch."

say "Creating safety backup"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$HOME/Downloads/catalyst-grit-before-v${VERSION}-${STAMP}.zip"
(
  cd "$(dirname "$REPO")"
  zip -qry "$BACKUP" "$(basename "$REPO")" -x '*/.git/*' '*/.venv/*' '*/__pycache__/*' '*/dist/*' '*/build/*'
)
printf 'Safety backup: %s\n' "$BACKUP"

say "Installing release source"
rsync -a --delete \
  --exclude='.git/' \
  --exclude='.env' \
  --exclude='.venv/' \
  --exclude='dist/' \
  --exclude='build/' \
  "$SOURCE/" "$REPO/"

say "Running portable release smoke tests"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
[ -n "$PYTHON_BIN" ] || fail "Python 3 is required."
(
  cd "$REPO"
  "$PYTHON_BIN" scripts/smoke_test.py
)

say "Recording Git release"
cd "$REPO"
git add -A
if git diff --cached --quiet; then
  printf 'No repository changes were required.\n'
else
  git commit -m "Catalyst Grit v$VERSION — $RELEASE_NAME"
fi

BRANCH="$(git branch --show-current)"
[ -n "$BRANCH" ] || fail "Repository is not on a named branch."
if [ "${SKIP_PUSH:-0}" = "1" ]; then
  printf 'SKIP_PUSH=1; Git push skipped.\n'
else
  say "Pushing $BRANCH"
  git push origin "$BRANCH"
fi

say "$PRODUCT v$VERSION installed successfully"
printf 'Repository: %s\n' "$REPO"
printf 'Branch: %s\n' "$BRANCH"
printf 'Backup: %s\n' "$BACKUP"
