# tripforge

Minimal input in, designed trip plan out. `tripforge plan` reads live nonstop flights (with flight numbers and times) from Google Flights and stays from Airbnb, adds visa, FX, travel advisory, climate and photos, and writes a self-contained `plan.html`, a `plan.png`, a `plan.json` and an `evidence/` folder.

Nothing is invented. If a fetch fails, the plan says "unavailable" for that cell.

## Install and run

```bash
uvx --from git+https://github.com/nitish7134/tripforge tripforge plan \
  --from BLR --stops "Phuket:2,Krabi:3,Bangkok:5" --start 2026-12-24 \
  --people 2 --budget-night 5000 --prefs veg,party --currency INR
```

(The repo is private, so use a machine where `gh auth login` / git credentials work.)

Local dev: `uv venv && uv pip install -e . && .venv/bin/tripforge --help`.

Browser: headless mode drives your installed Google Chrome through Playwright (no browser download). Playwright's own Chromium is the fallback (`playwright install chromium`).

## Options

| Option | Meaning |
| --- | --- |
| `--from` | Home airport IATA (BLR, DEL, BOM, ...) |
| `--stops` | `City:nights` list, optional `@IATA` override |
| `--start` | Arrival date at first stop; `--alt-start` (repeatable) adds more options to compare |
| `--people`, `--budget-night`, `--currency`, `--passport` | Group size, nightly stay budget, price currency, visa table passport |
| `--prefs` | Free tags such as `veg,party` (shown in the plan header) |
| `--hostels` | Also search cheap private rooms per stop |
| `--browser headless\|attach` | See below |
| `--out` | Output directory (default `out/`) |

`tripforge render out/plan.json --png` re-renders without refetching.

## Attach mode (your real Chrome)

Google or Airbnb may block headless browsers on some networks. `--browser attach` drives your logged-in Chrome through [playwright-cli](https://github.com/microsoft/playwright-cli) and its Chrome extension relay:

1. Install the Playwright Chrome extension, make sure `playwright-cli` is on PATH (or set `TRIPFORGE_PWCLI`), and Node 24+ is available (`TRIPFORGE_NODE_BIN` defaults to `/opt/homebrew/opt/node@24/bin`).
2. Run with `--browser attach`. tripforge uses session slug `tripforge` (`TRIPFORGE_SLUG` to change), opens its own tab and closes it afterwards.
3. Approve the connection in Chrome when prompted. The relay can drop; just rerun.

## Data sources (all keyless)

Google Flights page, Airbnb search page, frankfurter.app (FX), travel.state.gov RSS (US advisory), sunshineatlas.com MCP (climate normals), open-meteo (forecast, only within 16 days), Wikimedia Commons (photos, attribution kept). Visa info is a static, hand-maintained table in `src/tripforge/data/visa.json` with source links and a verify line. Daily spend ranges are labelled estimates.

## Limitations

- Scrapes page text; Google/Airbnb layout changes will break parsers. `tests/` has parser fixtures.
- Nonstop flights only. Stops without their own airport (for example Railay) are not modelled.
- Destinations come from `src/tripforge/data/places.json`; add cities there.
- Visa table covers a handful of countries for the Indian passport only.
- Day plans use curated highlights per destination, not live events.

## Trips folder and the planner agent

Each trip lives in `trips/<slug>/`: `brief.yaml` (inputs, however few), `notes.md` (decisions, friend constraints, open questions), `out/` (menu/plan PDF + HTML + PNG) and `evidence/` (every search screenshot). Example: `trips/thailand-dec26/`.

`agents/tripforge-planner.json` is a Kiro agent spec for a destination-agnostic trip planner: minimal input in, options menu out (dates with live fares, destination cards with fees and inclusions, events, priced combos, decision worksheet), then a detailed plan once you pick. Install with `cp agents/tripforge-planner.json ~/.kiro/agents/` and start a session with that agent. The agent never books anything; it gives links.

## Use it with your own AI agent (Claude, ChatGPT, Copilot, Cursor, Codex, Kiro)

tripforge is a CLI plus a prompt. Any agent that can run shell commands can drive it; any chat model can at least plan with the prompt. Three pieces:

| File | Purpose |
|---|---|
| `agents/PLANNER_PROMPT.md` | The planner behaviour as plain text. Paste it into any agent's system prompt / custom instructions. |
| `AGENTS.md` | Repo conventions for coding agents (Codex, Cursor, Aider, Gemini CLI read this automatically). |
| `agents/tripforge-planner.json` | Ready-made Kiro / Kiro Crew agent spec. |

### Claude Code
`CLAUDE.md` in the repo root already points at `AGENTS.md` and the prompt, so `claude` picks it up when started in this folder. Ask: *"Plan a 10-night Thailand trip from BLR around 24 Dec for 2 people, veg, party-friendly, ₹5k/night."* It will write `trips/<slug>/brief.yaml`, run `tripforge plan`, and hand you `trips/<slug>/out/plan.pdf`.

### Claude Desktop / Claude.ai Projects
Create a Project, paste `agents/PLANNER_PROMPT.md` into the project instructions, attach a trip's `out/plan.json` or `notes.md` when you want it to reason over results. Claude Desktop cannot run the CLI itself; run `tripforge plan` locally and upload the outputs, or connect a shell MCP server.

### ChatGPT (custom GPT or a Project)
Paste `agents/PLANNER_PROMPT.md` as the GPT's instructions. ChatGPT cannot execute `tripforge`, so use it for the options-menu reasoning and give it live numbers by uploading `plan.json` / the PDFs from `trips/<slug>/out/`. With Code Interpreter on it can read `plan.json` and recompute budgets with your own rates.

### GitHub Copilot (VS Code / Copilot Chat)
`.github/copilot-instructions.md` is already in the repo. Open the folder in VS Code, and Copilot Chat follows it. Agent mode can run `tripforge plan` in the terminal when you ask.

### Cursor / Windsurf / Codex CLI / Gemini CLI / Aider
All of these read `AGENTS.md` (Cursor also accepts it as a rule file). Open the repo and ask for a plan; they run the CLI and write to `trips/<slug>/`.

### Kiro / Kiro Crew
`cp agents/tripforge-planner.json ~/.kiro/agents/` and start a session with the `tripforge-planner` agent. The Kiro Crew skill lives at `~/.kiro/crew/skills/tripforge/SKILL.md`.

### No agent at all
```bash
uvx --from git+https://github.com/nitish7134/tripforge tripforge plan \
  --from BLR --stops "Bangkok:4,Koh Phangan:4,Krabi:2" --start 2026-12-24 \
  --people 2 --budget-night 5000 --prefs veg,party --trip thailand
open trips/thailand/out/plan.pdf
```

### Giving the agent your constraints
Put them in `trips/<slug>/brief.yaml` (see `trips/thailand-dec26/brief.yaml` for a full example: dates and alternatives, people, nonstop-only, stay budget, hostels OK, veg, per-meal and per-party-night rates, optional destination cards, must-consider questions). Any agent can read that file and the matching `notes.md`, so a plan started in one tool can be continued in another.

### What agents must not do
Book, pay, enter credentials, or invent prices. The prompt says so; keep it when you adapt it.
