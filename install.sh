#!/usr/bin/env bash
# WB2PPT installer — install this skill into agent-harness skill directories.
#
# Usage:
#   bash install.sh                 # auto-install into every detected harness
#   bash install.sh --list          # only show what was detected
#   bash install.sh --claude        # Claude Code        (~/.claude/skills/<name>)
#   bash install.sh --zcode         # ZCode              (~/.zcode/skills/<name>)
#   bash install.sh --agents        # openskills/.agents (~/.agents/skills/<name>)
#   bash install.sh --codex         # Codex CLI          (~/.codex/skills/<name>)
#   bash install.sh --project DIR   # project-level Claude Code skills (DIR/.claude/skills/<name>)
#   bash install.sh --rule-file F   # append a WB2PPT instruction line to rules file F
#                                   #   (AGENTS.md / .cursorrules / .clinerules / copilot-instructions.md)
#   bash install.sh --deps          # pip install python dependencies
#
# Requires: bash, python3. Python deps (requirements.txt) are needed at run time;
# LibreOffice is optional (only for the QA render step).

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="$(awk -F': *' '/^name:/{print $2; exit}' "$SRC/SKILL.md")"
[ -n "$NAME" ] || { echo "cannot read skill name from SKILL.md frontmatter"; exit 1; }

LIST_ONLY=0; DEPS=0; RULE_FILE=""
WANT_CLAUDE=0; WANT_ZCODE=0; WANT_AGENTS=0; WANT_CODEX=0; WANT_PROJECT=0; PROJECT_DIR=""
AUTO=1
next_project=0; next_rule=0
for arg in "$@"; do
  if [ "$next_project" = 1 ]; then PROJECT_DIR="$arg"; next_project=0; continue; fi
  if [ "$next_rule" = 1 ]; then RULE_FILE="$arg"; next_rule=0; continue; fi
  case "$arg" in
    --list)        LIST_ONLY=1 ;;
    --deps)        DEPS=1 ;;
    --claude)      WANT_CLAUDE=1; AUTO=0 ;;
    --zcode)       WANT_ZCODE=1; AUTO=0 ;;
    --agents)      WANT_AGENTS=1; AUTO=0 ;;
    --codex)       WANT_CODEX=1; AUTO=0 ;;
    --project)     next_project=1 ;;
    --project=*)   PROJECT_DIR="${arg#*=}" ;;
    --rule-file)   next_rule=1 ;;
    --rule-file=*) RULE_FILE="${arg#*=}" ;;
    *) echo "unknown arg: $arg"; exit 1 ;;
  esac
done
[ -n "$PROJECT_DIR" ] && { WANT_PROJECT=1; AUTO=0; }

install_to() {  # $1 = skills root dir
  local dest="$1/$NAME"
  mkdir -p "$1"
  if [ -d "$dest" ]; then
    if diff -qr -x '.git' -x '__pycache__' -x '.video_agent' "$SRC" "$dest" >/dev/null 2>&1; then
      echo "  = $dest (already up to date)"; return
    fi
    echo "  ~ $dest (updating)"
  else
    echo "  + $dest (new)"
  fi
  rm -rf "$dest"
  mkdir -p "$dest"
  (cd "$SRC" && tar cf - --exclude '.git' --exclude '__pycache__' --exclude '.video_agent' .) | tar xf - -C "$dest"
}

# -------- resolve targets --------
TARGETS=()
add_if() { [ -e "$1" ] && TARGETS+=("$2:$3") || true; }

if [ "$AUTO" = 1 ]; then
  add_if "$HOME/.claude"   "$HOME/.claude/skills"  "Claude Code"
  add_if "$HOME/.zcode"    "$HOME/.zcode/skills"   "ZCode"
  add_if "$HOME/.agents"   "$HOME/.agents/skills"  "openskills / .agents convention"
  add_if "$HOME/.codex"    "$HOME/.codex/skills"   "Codex CLI"
else
  [ "$WANT_CLAUDE" = 1 ] && TARGETS+=("$HOME/.claude/skills:Claude Code")
  [ "$WANT_ZCODE"  = 1 ] && TARGETS+=("$HOME/.zcode/skills:ZCode")
  [ "$WANT_AGENTS" = 1 ] && TARGETS+=("$HOME/.agents/skills:openskills / .agents convention")
  [ "$WANT_CODEX"  = 1 ] && TARGETS+=("$HOME/.codex/skills:Codex CLI")
  [ "$WANT_PROJECT" = 1 ] && { [ -n "$PROJECT_DIR" ] || { echo "--project needs a directory"; exit 1; }; \
      TARGETS+=("$PROJECT_DIR/.claude/skills:project-level Claude Code ($PROJECT_DIR)"); }
fi

echo "WB2PPT skill (name: $NAME) from: $SRC"
if [ "${#TARGETS[@]}" = 0 ]; then
  echo "no harness directories detected."
  echo "install explicitly, e.g.: bash install.sh --claude   |   --zcode   |   --agents   |   --project /path/to/repo"
else
  for t in ${TARGETS[@]+"${TARGETS[@]}"}; do
    root="${t%%:*}"; label="${t#*:}"
    [ "$LIST_ONLY" = 1 ] && { echo "  detected: $label -> $root"; continue; }
    echo "installing into $label:"
    install_to "$root"
  done
  [ "$LIST_ONLY" = 0 ] && echo "done."
fi

# -------- rule-file snippet (for harnesses without a skill dir: Codex/Cursor/Windsurf/Cline/Copilot) --------
if [ -n "$RULE_FILE" ] && [ "$RULE_FILE" != "__next__" ]; then
  if [ -f "$RULE_FILE" ] && grep -q "WB2PPT" "$RULE_FILE"; then
    echo "rule file $RULE_FILE already mentions WB2PPT — nothing appended."
  else
    cat >> "$RULE_FILE" <<EOF

<!-- WB2PPT skill -->
- Western-blot-to-PPT skill installed at "$SRC": when the user asks to organize Western Blot / WB
  raw data into a PPT (整理WB数据 / 整理Western Blot数据到PPT / 做WB结果PPT / organize Western blot
  images into PowerPoint), read "$SRC/SKILL.md" first and follow its phases exactly.
  Python deps: pip install -r "$SRC/requirements.txt" (LibreOffice needed only for the QA render).
EOF
    echo "snippet appended to $RULE_FILE"
  fi
fi

# -------- deps --------
if [ "$DEPS" = 1 ]; then
  echo "installing python dependencies..."
  python3 -m pip install -r "$SRC/requirements.txt"
fi

if [ "$LIST_ONLY" = 0 ]; then
  cat <<'TIP'

For rule-file harnesses (Codex / Cursor / Windsurf / Cline / Copilot), add the instruction
snippet to your rules file:
  bash install.sh --rule-file ~/.codex/AGENTS.md      # or .cursorrules, .clinerules, .github/copilot-instructions.md
TIP
fi
