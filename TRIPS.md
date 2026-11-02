# Where trip files go, and how to clean up

tripforge writes everything about one trip into **one folder**. Nothing else is created on your machine except a cache you can delete.

## Layout

```
<repo or any folder you run it from>/
  trips/
    <slug>/                 # one trip = one folder, e.g. trips/thailand-dec/
      brief.yaml            # your inputs (destination, dates, people, prefs, rates)
      notes.md              # decisions, constraints from friends, open questions
      out/
        menu.md             # options menu (from `tripforge menu`)
        plan.pdf            # the deliverable (from `tripforge plan`)
        plan.html / plan.png / plan.json
      evidence/             # one screenshot or JSON per search, with timestamps
  cache/
    tripforge.db            # sqlite cache of fetches (flights 8h, stays 24h, places 7d)
```

- `tripforge plan --trip <slug> ...` creates `trips/<slug>/` and writes the merged `brief.yaml`.
- `tripforge menu --brief trips/<slug>/brief.yaml` and `tripforge plan --brief ...` read from and write to that same folder.
- Run from anywhere: the `trips/` and `cache/` folders are created relative to your current directory, so you can keep trips completely outside the repo (for example `~/trips/`), and point at them with `--brief ~/trips/<slug>/brief.yaml`.

## Privacy

Trip folders contain personal data: your dates, home airport, who you travel with, screenshots of what you searched. In this repo `trips/` is **gitignored** (only `trips/README.md` and the sanitised `trips/example-thailand/` and `trips/example-lisbon-morocco/` are tracked). Keep real trips out of public git. If you want them versioned, use a private repo or a private fork.

## Cleaning up

| What | Command | Effect |
|---|---|---|
| One trip | `rm -rf trips/<slug>` | removes brief, notes, outputs and evidence for that trip |
| All trips | `rm -rf trips/*` and restore the tracked files with `git checkout -- trips/` | repo back to the example only |
| Cached fetches | `rm -rf cache/` | next run refetches everything |
| Browser state | nothing to clean: tripforge uses your installed Chrome headless, or Playwright's own Chromium if you installed it (`playwright uninstall chromium`) |

Nothing is written outside the folder you run from. If you installed the Kiro agent spec (`~/.kiro/agents/tripforge-planner.json`) or the Kiro Crew skill, those are the only files elsewhere; delete them to remove the agent.
