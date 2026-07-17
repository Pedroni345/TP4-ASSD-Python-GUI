# Reducing Claude Code context-token usage (setup notes)

Done on the main laptop on 2026-07-17. The repo-level part travels with this clone;
the machine-level part must be repeated on each PC.

## Already in this repo (nothing to do after cloning)

- `.claude/settings.json` — committed project settings with:
  - `permissions.deny` Read rules for `power_analyzer/` (legacy Python simulator,
    reference only), `STM32/CM4/` (unused core; we only use CM7), and
    `STM32/CM7/Debug/` (build artifacts). Claude Code has no `.claudeignore`;
    deny rules are the supported equivalent.
  - `claudeMdExcludes` for `~/.claude/rules/zh/**` (Chinese duplicates of common
    rules) and `~/.claude/rules/web/**` (irrelevant for firmware). ~13k
    tokens/session. Harmless no-op if those rules aren't installed.
- `CLAUDE.md` — tells every session where the active code lives so it doesn't
  explore dead directories.
- `.gitignore` — ignores `.claude/*` **except** `settings.json` so the shared
  settings stay tracked.

## To repeat on each machine (~8k tokens/session + smaller subagents)

The `everything-claude-code` (ECC) plugin and its `install.sh` both install the
same content, so `~/.claude/{skills,agents,commands}` end up as byte-identical
copies of the plugin — and both get listed in every session AND in every
subagent's context (this is what filled the Haiku agents' 200k windows).

**Keep the plugin, remove the loose copies** — the plugin is the superset
(more skills, the MCP servers: Context7/GitHub/Playwright/Exa, auto-updates).
Do NOT uninstall the plugin.

1. Verify the duplication first (don't delete blind):

   ```bash
   P=$(ls -d ~/.claude/plugins/cache/everything-claude-code/everything-claude-code/*/ | tail -1)
   comm -12 <(ls ~/.claude/skills | sort) <(ls "$P/skills" | sort) | wc -l   # dupes
   comm -23 <(ls ~/.claude/skills | sort) <(ls "$P/skills" | sort)           # yours only — KEEP these
   # same idea for ~/.claude/agents and ~/.claude/commands
   ```

2. Move (don't delete) the duplicates to a backup, keeping anything that is
   yours only (e.g. the `learned` skill from continuous-learning):

   ```bash
   B=~/.claude/ecc-duplicates-backup-$(date +%F); mkdir -p "$B"/{skills,agents,commands}
   for d in ~/.claude/skills/*/; do n=$(basename "$d"); [ "$n" = learned ] && continue; mv "$d" "$B/skills/"; done
   mv ~/.claude/agents/*   "$B/agents/"
   mv ~/.claude/commands/* "$B/commands/"
   ```

3. Restart Claude Code and check with `/context` — skills/agents listing should
   roughly halve; memory files should drop ~13k.

Undo anytime by moving the backup contents back.
