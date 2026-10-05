# tracker

An agent-run work-output + fitness tracker. You talk; an AI agent turns it into
calendar events and a local dashboard. Three things get captured — **work**, **diet**,
**exercise** — and surfaced as two headline numbers (Mobilization, Efficiency) plus
fitness gauges and a rolling-average "ticker."

The design premise: **you never maintain this by hand.** You tell your agent what
happened ("1h deep work, felt like a 4; then gym 45min; lunch was a chicken bowl ~700cal
45g protein"), and the agent files it. If you're reading this, your agent should read
[`AGENT.md`](AGENT.md) — that's the operating manual.

## What's here

```
AGENT.md          operating guide for the agent (the important file)
README.md         this file
tracker/
  calwrite.swift        EventKit writer (agent creates/updates/deletes events)
  fetch_evidence.swift  EventKit reader (pulls the calendar as TSV)
  build_data.py         parses events → data.json (daily Mob/Eff + fitness)
  index.html            the dashboard (open in a browser)
  refresh.sh            fetch → build → done
logs/
  _TEMPLATE.md          blank day-log format
  EXAMPLE-2026-01-02.md a filled example day
foods.example.md  starter food-macro library (copy to foods.md and grow it)
```

## Requirements

- macOS (uses EventKit / Apple Calendar).
- Xcode command-line tools (`swiftc`) — `xcode-select --install`.
- Python 3.9+ (`zoneinfo` is stdlib).
- A calendar app signed into iCloud (for cloud backup of your data).

## Setup

1. **Make two calendars** in Calendar.app (second is optional):
   - `Evidence.` — what actually happened.
   - `Intention` — plans (optional).
   If you rename them, update `CALENDAR_NAME` in `tracker/fetch_evidence.swift` and
   `DEFAULT_CAL` in `tracker/calwrite.swift` to match.

2. **Set your config** (all clearly marked at the top of each file):
   - `tracker/build_data.py`: `CANONICAL_TZ` (your home timezone), `START_DATE_ISO`,
     `FITNESS_TARGETS`.
   - `tracker/fetch_evidence.swift`: `PULL_FROM` (start date).

3. **Grant calendar access.** The first run of either Swift tool triggers the macOS
   permission prompt — allow it. `refresh.sh` compiles `fetch_evidence` automatically;
   compile the writer once with:
   ```bash
   swiftc -O tracker/calwrite.swift -o tracker/calwrite
   ```

4. **Run it:**
   ```bash
   bash tracker/refresh.sh      # pulls the calendar, builds data.json
   open tracker/index.html      # view the dashboard
   ```

## Daily use

You don't run anything — your agent does. It writes events as you report them, keeps the
`logs/` markdown in sync, and re-runs `refresh.sh`. You just open `index.html` (or leave
it open; it auto-reloads the local data).

Everything regenerates from the calendar, so the calendar (iCloud-synced) is your real
backup. The only data that *only* lives in the logs is the human-readable food
descriptions — the macro numbers are in the calendar tags.

## Not included (lives in the original, left out as personal/era-specific)

- An hour-of-day "breakdown" analysis (per-era smoothed Mobilization × Efficiency).
- A voice → calendar bridge.

Both are easy to add back; they were cut to keep this package lean and generic.
