# SECURITY.md

## Secrets handling
- Secrets never live in code or in git.
- **Locally:** in `.env` (git-ignored). `.env.example` documents the names only.
- **In CI:** GitHub → Settings → Secrets and variables → Actions:
  `AMADEUS_CLIENT_ID`, `AMADEUS_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## Action required — rotate v1 keys
The v1 SerpApi key and Telegram bot token were exposed during development. Rotate them:
- Telegram: message **@BotFather** → `/revoke` → use the new token.
- SerpApi: regenerate in the SerpApi dashboard (only if you keep using it).

## Other measures
- All outbound API calls use HTTPS.
- Validator rejects any unverifiable offer; the app never invents data.
- API call volume is capped (Phase 5) to avoid runaway cost.
- The committed SQLite history contains only public fare data — no secrets.
- A secret-leak scan (`scripts/check_secrets.py`) runs in CI on every push and
  fails the build if a token-shaped string appears in a tracked file. Run it
  locally any time with `python scripts/check_secrets.py`.
- **Logs are redacted at the source.** `log.py` runs every record through a
  redaction filter that strips Telegram bot tokens, `api_key=` query params, and
  `Bearer` tokens. This protects against `requests` exceptions embedding the
  request URL (with its secret) in a logged error message.
