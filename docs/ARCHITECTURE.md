# ARCHITECTURE.md

```mermaid
flowchart TD
    SCHED[GitHub Actions cron<br/>every 8h + manual button] --> MAIN[main.py]

    subgraph PIPE[flightguru pipeline]
        SEARCH[search.py<br/>Amadeus offers]
        NORM[normalize.py<br/>clean + validate, reject junk]
        LINK[deeplink.py<br/>booking URL or none]
        STORE[storage.py<br/>SQLite history]
        DELTA[delta.py<br/>compare vs last + target]
        NOTIFY[notify.py<br/>Telegram]
    end

    MAIN --> SEARCH --> NORM --> LINK --> STORE --> DELTA
    DELTA -->|alert warranted| NOTIFY
    DELTA -->|no link / not cheaper| LOG[log only, no alert]

    SEARCH <-->|HTTPS| AMADEUS[(Amadeus API)]
    STORE <--> DB[(data/flightguru.db<br/>committed back each run)]
    NOTIFY --> TG[(Telegram)]
```

## Components
- **main.py** — entry point; runs the steps in order and handles errors.
- **search.py** — asks Amadeus for fares (Phase 2).
- **normalize.py** — validates and cleans; home of the "never invent data" rule (Phase 2).
- **deeplink.py** — builds a booking link or returns None (Phase 2).
- **storage.py** — SQLite read/write (Phase 3).
- **delta.py** — decides whether to alert (Phase 3).
- **notify.py** — sends Telegram, plain text (Phase 4).

## Why GitHub Actions instead of a server
The job is periodic, not always-on. A scheduled workflow is free, needs no
server to manage, and committing the SQLite file back each run both persists
history and keeps the schedule alive. See [DECISIONS.md](DECISIONS.md).
