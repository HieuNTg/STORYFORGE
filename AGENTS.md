# StoryForge — Working agreement

## Codebase navigation (IMPORTANT)

This project has 700+ files. Do NOT blind-Read or blind-Grep the codebase.

**Prefer Serena MCP tools over Read/Grep for any code task that crosses files:**

- `mcp__serena__find_symbol` — locate a function/class/method by name
- `mcp__serena__find_referencing_symbols` — find every callsite/import of a symbol BEFORE refactoring
- `mcp__serena__get_symbols_overview` — get the shape of a file without reading every line
- `mcp__serena__search_for_pattern` — symbol-aware search

**Rule:** Before editing any function or class, run `find_referencing_symbols` to see who depends on it. Do not refactor without that impact list.

For architecture-level questions (layers, tour, project shape), read `.understand-anything/knowledge-graph.json` instead of crawling source.

For one-file local edits with no cross-file impact, normal Read/Edit is fine.

## Product constraints

- Vietnamese names default; Chinese names only for tiên hiệp/wuxia genre
- No video / no TTS — image-focused (consistent character visuals + dialogue)
- Open-source build: no auth guards required
- L1 (story) and L2 (enhance) pipelines are independent
- Simulator and Debate stay in strict lanes: simulator = plot/drama, debate = craft critique only

## Git workflow

- Single sprint branch, one PR to master
- Never merge dependabot PRs
