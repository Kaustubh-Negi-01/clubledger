# Database: SQLite schema and local storage

`migrations/` contains the SQL files that create tables, indexes and triggers. `runtime/` holds local databases, generated simulator secrets and receipt uploads; its contents are ignored by Git.

The preview database is `runtime/clubledger-preview.db`. It was copied through SQLite's backup API from the previous preview so existing purchases and memberships are preserved. Tests create separate temporary databases.

## Migration order

| File | Creates or protects |
| --- | --- |
| `0001_core.sql` | Users, roles, permissions, sessions, terms, audit and idempotency records |
| `0002_payments.sql` | Payments and verified payment events |
| `0003_membership.sql` | Membership plans and memberships |
| `0004_events.sql` | Events, ticket holds and tickets |
| `0005_store.sql` | Products, variants, orders and order items |
| `0006_journal.sql` | Accounts, journal entries/lines and financial protection triggers |
| `0007_tasks.sql` | Fundraisers and tasks |
| `0008_expenses.sql` | Expenses and receipt metadata |
| `0009_comms.sql` | Announcements, subscribers, mail outbox and capture |
| `0010_close.sql` | Close checks, snapshots and officer handover |

Migration contents were deliberately preserved byte-for-byte during reorganization. Once a migration has run, its checksum is stored in `schema_migrations`. Change the schema through a new numbered migration, not by editing an applied one.

## Concepts to know

- **Table:** a group of similarly shaped records, such as users or orders.
- **Primary key:** a record's unique identity, usually `id`.
- **Foreign key:** a link to a record in another table.
- **Constraint:** a database rule, such as nonnegative stock or a unique ticket code.
- **Index:** an aid for finding records efficiently.
- **Transaction:** several changes succeed together or are rolled back together.
- **Trigger:** a database rule that automatically checks a write; journal triggers prevent changes to posted entries.
- **Paise:** money is stored as integers; `100` paise means ₹1.00.
- **WAL:** SQLite's write-ahead log; do not copy only the main database file while the app is writing. Use SQLite backup.

The preview has 35 application tables. The schema export in `docs/DATABASE_STRUCTURE.md` lists exact columns, relationships and SQL. It contains no private record contents.

Run `python -m clubledger.cli migrate` to apply pending migrations. `check-integrity` validates accounting links and balances; it does not reset data.
