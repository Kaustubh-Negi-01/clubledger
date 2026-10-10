# Configuration and integrations

`.env` is a text file, not a directory. It belongs at the repository root and is ignored by Git. `.env.example` is the shareable template. This folder documents configuration without storing private credentials.

`backend/clubledger/config.py` loads the root `.env` using python-dotenv. Explicit shell environment variables take priority.

| Setting | Meaning |
| --- | --- |
| `CLUBLEDGER_ENV` | `dev`, `test` or `prod`; development binds only to loopback |
| `CLUBLEDGER_HOST` | Address the server listens on; use `127.0.0.1` for local work |
| `CLUBLEDGER_PORT` | Local port; our preview uses `8010` |
| `CLUBLEDGER_DB_PATH` | SQLite database file; defaults to `database/runtime/clubledger.db` |
| `CLUBLEDGER_SIM_SECRET` | Signs and validates simulated payment callbacks; required in prod |
| `CLUBLEDGER_RECEIPTS_DIR` | Optional private receipt directory; defaults next to the database |
| `CLUBLEDGER_DEMO_TIME` | Optional development-only simulated UTC clock, controlled by demo tools |

## Which APIs are actually used?

- **Internal HTTP APIs:** FastAPI routes under `backend/clubledger/api/`. See `docs/API_REFERENCE.md` for the extracted endpoint list.
- **Payment gateway:** local simulator. No Stripe/Razorpay integration or real bank/card charge.
- **Email:** local outbox and capture tables. No SMTP delivery service.
- **AI:** no runtime Gemini, Claude or OpenAI API integration. Those tools assisted development; subscriptions are not application dependencies.
- **Fonts and graphics:** hosted locally; no external font service is needed at runtime.

The simulator signature secret is a shared secret, not a paid-provider API key. In development it can be generated into `.sim_secret` next to the database. Keep secrets and database runtime files out of commits.
