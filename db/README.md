# PM Assistant — database schema

PostgreSQL schema for a LINE-based AI assistant that helps IT project managers:
turn meeting notes into ISO 29110 work products, create tasks/cards on
Jira/ClickUp, manage calendar events, and send reminders.

Schema file: `schema.sql` (PostgreSQL 15+, tested syntax for Railway Postgres).

## Table groups

**Identity & projects** — `users`, `projects`, `project_members`, `line_contexts`
Resolves which project an incoming LINE message belongs to and who the team is.

**Multi-platform** — `connections`, `project_bindings`
`connections` = an authenticated account (Jira/ClickUp/Google) connected once.
`project_bindings` = per project, which connection handles each capability
(`tasks` / `calendar` / `docs` / `email` / `notify`). This is what lets one
project route tasks to ClickUp while another uses Jira, with no code change.

**Documents** — `document_templates`, `document_number_sequences`, `documents`
Templates are uploaded .docx with placeholders. Numbers are configured per
project per work product type. `documents` stores both the structured `data`
and the rendered file.

**Meetings** — `meetings`, `meeting_attendees`, `action_items`
`action_items.is_inferred` flags items the LLM guessed (the "ระบบเดา" tag).

**Delivery work** — `milestones`, `tasks` (with `external_ref` to the synced card)

**ISO 29110 SI** — `requirements`, `test_cases`, `traceability_links`
The traceability matrix renders from `traceability_links`; each row links a
requirement to either a task (implements) or a test case (verifies).

**Calendar** — `calendar_events`, `calendar_event_attendees`

**Confirmation** — `pending_confirmations`
Backs the human-in-the-loop flow: a draft is stored with `expires_at`; the
adapters only run after the user confirms before expiry.

**Notifications** — `notification_preferences`, `scheduled_notifications`
A scheduler inserts/queues rows; a worker pushes to LINE when due.

**Audit** — `audit_log` (who did what, for ISO traceability).

## Document numbering (per project)

Each `document_number_sequences` row has a `pattern` (e.g. `{KEY}-{TYPE}-{SEQ:04d}`),
a `prefix`, a `current_seq`, and an optional yearly reset. Assign a number
atomically when issuing a document, inside one transaction:

```sql
BEGIN;
UPDATE document_number_sequences
   SET current_seq = CASE
         WHEN reset_period = 'yearly' AND last_reset_year < EXTRACT(year FROM now())::int
           THEN 1 ELSE current_seq + 1 END,
       last_reset_year = EXTRACT(year FROM now())::int
 WHERE project_id = $1 AND wp_type = $2
 RETURNING current_seq, prefix, pattern;
-- format the returned values in app code -> 'HR-MIN-0007', write to documents.doc_number
COMMIT;
```

`SELECT ... FOR UPDATE` is implicit in the `UPDATE`, so concurrent issues won't
collide.

## Deploy on Railway

1. Add a PostgreSQL service in your Railway project; copy the `DATABASE_URL`.
2. Apply the schema:
   ```bash
   psql "$DATABASE_URL" -f schema.sql
   ```
3. Store `DATABASE_URL` as an env var in your backend service. Connection
   credentials in the `connections` table must be encrypted in app code before
   insert (e.g. with a key from `APP_ENCRYPTION_KEY`) — the DB only holds ciphertext.

## Using this in Cursor

Paste `schema.sql` into Cursor and prompt, for example:

> Generate SQLAlchemy (or Prisma) models from this schema, plus a repository
> layer. Then implement a `get_next_doc_number(project_id, wp_type)` function
> following the numbering transaction in the README.

Or:

> Implement the `TaskTracker` port and a `ClickUpAdapter` that maps the `tasks`
> table's canonical fields to ClickUp's API, using `project_bindings.config`.
