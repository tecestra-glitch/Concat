#!/usr/bin/env bash
# discover.sh — busca MCPs, repos e skills relevantes para um projeto
# Uso: ./discover.sh "descrição do projeto" [output_dir]
# Requer: gh CLI, jq

set -euo pipefail

QUERY="${1:-}"
OUT="${2:-./dev/discovery}"
mkdir -p "$OUT"

if [ -z "$QUERY" ]; then
  echo "Uso: $0 'descrição do projeto' [output_dir]" >&2
  exit 1
fi

echo "🔍 Buscando recursos para: $QUERY"
echo ""

# ── Skills já instaladas ───────────────────────────────────────────────
echo "## Skills instaladas" > "$OUT/skills.md"
# Skills do usuário, do projeto atual e da raiz do repositório (o projeto pode ser uma subpasta).
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
{ for b in "$HOME/.claude/skills" ".claude/skills" ${ROOT:+"$ROOT/.claude/skills"}; do
    if [ -d "$b" ]; then realpath "$b"; fi
  done; } | sort -u | while read -r base; do
  find "$base" -name "SKILL.md" | while read -r f; do
    # `|| true`: um SKILL.md sem frontmatter não pode derrubar o script (set -euo pipefail)
    name=$(grep '^name:' "$f" 2>/dev/null | head -1 | cut -d: -f2 | xargs || true)
    desc=$(grep '^description:' "$f" 2>/dev/null | head -1 | cut -d: -f2- | xargs || true)
    echo "- **$name**: $desc ($(dirname "$f"))" >> "$OUT/skills.md"
  done
done
echo "Skills salvas em $OUT/skills.md"

# ── MCPs do projeto atual ─────────────────────────────────────────────
echo "## MCPs configurados" > "$OUT/mcps-atuais.md"
if [ -f ".mcp.json" ]; then
  # servidores stdio mostram command + args; servidores http/sse mostram .url
  jq -r '.mcpServers | to_entries[] | "- **\(.key)**: \(if .value.url then (.value.type // "http") + " " + .value.url else ((.value.command // "") + " " + ((.value.args // []) | join(" "))) end)"' .mcp.json >> "$OUT/mcps-atuais.md" 2>/dev/null || echo "(nenhum)" >> "$OUT/mcps-atuais.md"
else
  echo "(sem .mcp.json)" >> "$OUT/mcps-atuais.md"
fi
echo "MCPs atuais salvos em $OUT/mcps-atuais.md"

# ── Repos GitHub relacionados ─────────────────────────────────────────
echo "## Repositórios relacionados" > "$OUT/repos.md"
if command -v gh &>/dev/null; then
  SLUG=$(echo "$QUERY" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | cut -c1-60)
  gh api -X GET search/repositories \
    -f q="$QUERY in:description,name language:TypeScript language:Python stars:>50" \
    -f sort=stars -f order=desc -f per_page=10 \
    --jq '.items[] | "- [\(.full_name)](\(.html_url)) ⭐\(.stargazers_count) — \(.description // "")"' \
    >> "$OUT/repos.md" 2>/dev/null || echo "(busca falhou)" >> "$OUT/repos.md"
else
  echo "(gh CLI não disponível)" >> "$OUT/repos.md"
fi
echo "Repos salvos em $OUT/repos.md"

# ── Sumário ───────────────────────────────────────────────────────────
echo ""
echo "✅ Discovery concluído em $OUT/"
echo "   - $OUT/skills.md"
echo "   - $OUT/mcps-atuais.md"
echo "   - $OUT/repos.md"
