# ClubLedger

One platform for a student club: memberships, event tickets, merchandise, announcements, fundraiser tasks, expenses and the club's books. Built for the Skyline Student Association.

- **App:** Next.js 16 (App Router, Server Actions), TypeScript, Tailwind v4, Motion
- **Database and auth:** Supabase (Postgres, Google sign-in, email and magic link)
- **Hosting:** Vercel
- **Business rules:** live in Postgres as `api_*` functions, so every rule is transactional and tested in SQL

Money is stored as integer paise. Payments in this build go through a simulated gateway: nothing real is charged.

## Run it now (no accounts needed)

```bash
npm install
npm run dev
```

Open http://localhost:3000. With no Supabase variables set, the app runs on a built-in demo club (the real migrations and a demo seed, in an in-process Postgres). On the sign-in page pick a person:

| Person | Role | Try this |
|---|---|---|
| Maya Fernandes | Member | Member prices, tickets, orders, expenses |
| Dev Malhotra | Signed up, not a member | Pays public prices, joins, pays dues |
| Ishaan Verma | Door and store | `/admin/checkin`, hand over orders |
| Rohan Kapoor | Treasurer | Payments, expenses, finance, close the term |
| Priya Nair | President (admin) | Events, announcements, team, handover |

The admin overview has **Demo controls** to skip the clock, so you can watch holds expire, a late payment land as an obligation, and a term close.

## Connect Supabase (production database)

1. Create a project at supabase.com.
2. Apply the schema. Either run the SQL files in `supabase/migrations/` in order in the SQL editor, or use the CLI:
   ```bash
   npx supabase link --project-ref <ref>
   npx supabase db push
   ```
   Migrations are applied strictly in number order (`0001` to `0010`). Do not add placeholder files.
3. **Auth > Providers > Google:** enable it with your Google OAuth client ID and secret (create one in Google Cloud Console, type "Web application").
   - Authorized redirect URI in Google: `https://<ref>.supabase.co/auth/v1/callback`
4. **Auth > URL configuration:** set the Site URL to your Vercel URL and add `https://<your-domain>/auth/callback` (and `http://localhost:3000/auth/callback`) to the redirect allow-list.
5. Copy the project URL, anon key and service-role key into `.env.local` (see `.env.example`).
6. Sign in once. **The first account to sign in becomes the admin**, so do this yourself right after deploying; grant everyone else roles from `/admin/team`.
7. In `/admin/team` > Deployment settings: restrict sign-ups to your college's email domain (enforced by the database) and, when a real payment gateway is attached, switch **simulated payments off**. While it is on, any signed-in person can confirm their own checkout.

Tables are private (row level security on, no grants). The browser and server only reach data through `api_*` functions, which check who is calling. The service-role key is used only for receipt storage and the cron route.

### Firebase later

Authentication sits behind `src/lib/session.ts` and `src/lib/db/index.ts`. Supabase Auth is wired today. To add Firebase sign-in, mint a Supabase-compatible JWT for the Firebase user (or enable Supabase's third-party auth for Firebase) so `auth.uid()` still resolves inside the database. No business logic needs to change.

## Deploy on Vercel

1. Import the repository in Vercel (framework: Next.js).
2. Add the environment variables from `.env.example`. Set `NEXT_PUBLIC_SITE_URL` to the production URL.
3. `vercel.json` schedules `/api/cron/maintenance` daily (expires holds and reservations, queues renewal reminders). Set `CRON_SECRET`; Vercel sends it as a bearer token.
4. Deploy. Without credentials the app falls back to the demo database, which is fine for a preview but resets on every cold start.

## Test it

```bash
npm run test:db      # 130+ SQL behaviour tests against the real migrations (no services needed)
npm run build && npm start -- -p 3200
npm run test:e2e     # drives real Chromium through every flow against localhost:3200
```

`test:e2e` needs a Chromium (Playwright's cache or `CHROME_PATH`) and writes screenshots to `shots/`.

## What is where

```
supabase/migrations/   schema, ledger triggers, api_* functions, security (applied in order)
supabase/dev/          demo seed and the Supabase stand-ins used by the demo database and tests
src/app/(site)/        public site and member area
src/app/admin/         officer console (role-gated)
src/app/actions/       server actions (all writes)
src/lib/db/            the single door to the database (Supabase or demo)
docs/                  the original contract, requirements and build order
scripts/               SQL tests and browser tests
```

## Rules the system enforces

- A registered account is not a membership. Only paid dues unlock member prices; non-members buy at public prices. Buying needs a sign-in.
- Prices, capacity and stock are decided on the server. Seats and sizes are held for the whole order, or not at all.
- A payment that arrives after its reservation expired is never discarded: it becomes an obligation the treasurer refunds or completes.
- Refunds are full and reverse the ledger exactly. A used ticket or picked-up order cannot be refunded.
- Posted ledger entries are immutable (database triggers). Closing a term seals a checksummed snapshot, opens the next term, and carries every balance forward.
- Roles take effect immediately; nothing about permissions is cached.

`docs/STACK_DECISION.md` explains how this stack replaces the Python plan in the original contract and which contract rules were kept.
