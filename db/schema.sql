-- =============================================================================
-- PM Assistant — PostgreSQL schema
-- Target: PostgreSQL 15+ (Railway).  Run:  psql "$DATABASE_URL" -f schema.sql
--
-- Design notes:
--  * Core never depends on a specific vendor. Tasks/docs/events store a
--    canonical shape; the link to Jira/ClickUp/Google lives in `connections`
--    + `project_bindings` + an `external_ref` jsonb on each synced row.
--  * Platform credentials are stored ENCRYPTED at the application layer; the
--    DB only holds ciphertext in `connections.credentials`.
--  * Soft, flexible fields use jsonb so adapters can map vendor-specific data
--    without schema changes.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid(), digest()

-- ---------------------------------------------------------------------------
-- Enumerated types (small, stable sets)
-- ---------------------------------------------------------------------------
CREATE TYPE connection_type    AS ENUM ('jira','clickup','google','gmail','line','other');
CREATE TYPE capability         AS ENUM ('tasks','calendar','docs','email','notify');
CREATE TYPE work_product_type  AS ENUM ('meeting_record','memo','project_plan','requirements','traceability','test_case','change_request');
CREATE TYPE task_status        AS ENUM ('todo','in_progress','blocked','done','cancelled');
CREATE TYPE task_priority      AS ENUM ('low','medium','high','urgent');
CREATE TYPE doc_status         AS ENUM ('draft','issued');
CREATE TYPE milestone_status   AS ENUM ('open','at_risk','done');
CREATE TYPE confirmation_status AS ENUM ('pending','confirmed','cancelled','expired');
CREATE TYPE notification_type  AS ENUM ('due_soon','overdue','meeting_soon','status_change','milestone_due');
CREATE TYPE number_reset       AS ENUM ('none','yearly');

-- Generic updated_at trigger
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Identity & projects
-- ---------------------------------------------------------------------------

-- People who use the bot (PMs). Identified primarily by their LINE user id.
CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  line_user_id  text UNIQUE NOT NULL,            -- LINE userId from webhook
  display_name  text,
  email         text,
  timezone      text NOT NULL DEFAULT 'Asia/Bangkok',
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE projects (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key           text NOT NULL,                   -- short code used in doc numbers, e.g. 'HR'
  name          text NOT NULL,
  owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  is_archived   boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (owner_user_id, key)
);
CREATE TRIGGER trg_projects_updated BEFORE UPDATE ON projects
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Project team. Used to resolve "name -> email" for calendar invites / assignees.
CREATE TABLE project_members (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name        text NOT NULL,
  email       text,
  role        text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_members_project ON project_members(project_id);

-- Maps a LINE conversation (1:1, group, or room) to the active project,
-- so the bot knows which project an incoming message belongs to.
CREATE TABLE line_contexts (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  line_source_type  text NOT NULL CHECK (line_source_type IN ('user','group','room')),
  line_source_id    text NOT NULL,               -- userId / groupId / roomId
  project_id        uuid REFERENCES projects(id) ON DELETE SET NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (line_source_type, line_source_id)
);
CREATE TRIGGER trg_line_ctx_updated BEFORE UPDATE ON line_contexts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Multi-platform connections & per-project routing
-- ---------------------------------------------------------------------------

-- An authenticated account on an external platform. Connected once, reusable
-- across projects. One Google connection can serve calendar + docs + email.
CREATE TABLE connections (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type          connection_type NOT NULL,
  display_name  text NOT NULL,                   -- e.g. 'ClickUp (work)'
  credentials   jsonb NOT NULL DEFAULT '{}',     -- ENCRYPTED ciphertext only
  metadata      jsonb NOT NULL DEFAULT '{}',     -- site url, account id, scopes...
  status        text NOT NULL DEFAULT 'connected' CHECK (status IN ('connected','expired','error','revoked')),
  expires_at    timestamptz,                     -- for OAuth token expiry
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_connections_owner ON connections(owner_user_id);
CREATE TRIGGER trg_connections_updated BEFORE UPDATE ON connections
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Which connection a project uses for each capability. One row per capability.
-- `config` holds adapter-specific routing (Jira project key, ClickUp list id,
-- Google calendar id, field mapping, etc.).
CREATE TABLE project_bindings (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  capability    capability NOT NULL,
  connection_id uuid NOT NULL REFERENCES connections(id) ON DELETE RESTRICT,
  config        jsonb NOT NULL DEFAULT '{}',
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, capability)
);
CREATE TRIGGER trg_bindings_updated BEFORE UPDATE ON project_bindings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Document templates, numbering, and generated work products
-- ---------------------------------------------------------------------------

-- Uploaded .docx templates (with placeholders) per project per work product.
CREATE TABLE document_templates (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  wp_type       work_product_type NOT NULL,
  file_ref      text NOT NULL,                   -- storage path / object key
  field_map     jsonb NOT NULL DEFAULT '{}',     -- canonical field -> placeholder
  version       int NOT NULL DEFAULT 1,
  uploaded_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, wp_type, version)
);

-- Per-project, per-type running number config (answers Q1). The pattern uses
-- tokens like {KEY}, {TYPE}, {SEQ:04d}, {YYYY}. `current_seq` is incremented
-- atomically (see README) when a document is issued.
CREATE TABLE document_number_sequences (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  wp_type         work_product_type NOT NULL,
  prefix          text NOT NULL,                 -- e.g. 'MIN'
  pattern         text NOT NULL DEFAULT '{KEY}-{TYPE}-{SEQ:04d}',
  current_seq     int NOT NULL DEFAULT 0,
  reset_period    number_reset NOT NULL DEFAULT 'none',
  last_reset_year int,
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, wp_type)
);
CREATE TRIGGER trg_numseq_updated BEFORE UPDATE ON document_number_sequences
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- A generated work product instance (the rendered document + its data).
CREATE TABLE documents (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  wp_type       work_product_type NOT NULL,
  doc_number    text,                            -- assigned on issue, e.g. 'HR-MIN-0007'
  title         text NOT NULL,
  data          jsonb NOT NULL DEFAULT '{}',     -- the structured content used to render
  file_ref      text,                            -- rendered .docx/.pdf location
  status        doc_status NOT NULL DEFAULT 'draft',
  source_type   text,                            -- 'meeting' | 'manual' | ...
  source_id     uuid,                            -- e.g. meetings.id
  created_by    uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  issued_at     timestamptz
);
CREATE INDEX idx_documents_project ON documents(project_id, wp_type);

-- ---------------------------------------------------------------------------
-- Meetings & action items
-- ---------------------------------------------------------------------------

CREATE TABLE meetings (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title             text NOT NULL,
  meeting_date      date,
  raw_notes         text,                        -- original pasted/transcribed text
  decisions         jsonb NOT NULL DEFAULT '[]', -- array of decision strings
  calendar_event_id uuid,                        -- optional link to calendar_events
  created_by        uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_meetings_project ON meetings(project_id);

CREATE TABLE meeting_attendees (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_id  uuid NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
  member_id   uuid REFERENCES project_members(id) ON DELETE SET NULL,
  name        text,                              -- fallback for non-members
  email       text
);
CREATE INDEX idx_attendees_meeting ON meeting_attendees(meeting_id);

CREATE TABLE action_items (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_id    uuid NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
  project_id    uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  description   text NOT NULL,
  owner_id      uuid REFERENCES project_members(id) ON DELETE SET NULL,
  due_date      date,
  is_inferred   boolean NOT NULL DEFAULT false,  -- the "ระบบเดา" flag
  task_id       uuid,                            -- set when promoted to a task
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_action_items_meeting ON action_items(meeting_id);

-- ---------------------------------------------------------------------------
-- Milestones, tasks
-- ---------------------------------------------------------------------------

CREATE TABLE milestones (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name          text NOT NULL,
  description   text,
  target_date   date,
  status        milestone_status NOT NULL DEFAULT 'open',
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_milestones_project ON milestones(project_id);
CREATE TRIGGER trg_milestones_updated BEFORE UPDATE ON milestones
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE tasks (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title           text NOT NULL,
  description     text,
  assignee_id     uuid REFERENCES project_members(id) ON DELETE SET NULL,
  due_date        date,
  priority        task_priority NOT NULL DEFAULT 'medium',
  status          task_status NOT NULL DEFAULT 'todo',
  milestone_id    uuid REFERENCES milestones(id) ON DELETE SET NULL,
  external_ref    jsonb NOT NULL DEFAULT '{}',   -- {connection_id, provider, key:'HR-128', url}
  created_by      uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_tasks_project ON tasks(project_id);
CREATE INDEX idx_tasks_due ON tasks(due_date) WHERE status NOT IN ('done','cancelled');
CREATE INDEX idx_tasks_milestone ON tasks(milestone_id);
CREATE TRIGGER trg_tasks_updated BEFORE UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- ISO 29110 SI work products: requirements, test cases, traceability
-- ---------------------------------------------------------------------------

CREATE TABLE requirements (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  code          text NOT NULL,                   -- e.g. 'REQ-012'
  title         text NOT NULL,
  description   text,
  status        text NOT NULL DEFAULT 'open',
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, code)
);

CREATE TABLE test_cases (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  code            text NOT NULL,                 -- e.g. 'TC-031'
  requirement_id  uuid REFERENCES requirements(id) ON DELETE SET NULL,
  title           text NOT NULL,
  steps           jsonb NOT NULL DEFAULT '[]',
  expected_result text,
  status          text NOT NULL DEFAULT 'draft',
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, code)
);
CREATE INDEX idx_testcases_req ON test_cases(requirement_id);

-- The Traceability Record. Each row links a requirement to EITHER a task
-- (implements) OR a test case (verifies). The matrix document renders from this.
CREATE TABLE traceability_links (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  requirement_id  uuid NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
  task_id         uuid REFERENCES tasks(id) ON DELETE CASCADE,
  test_case_id    uuid REFERENCES test_cases(id) ON DELETE CASCADE,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CHECK ((task_id IS NOT NULL) <> (test_case_id IS NOT NULL))  -- exactly one
);
CREATE INDEX idx_trace_req ON traceability_links(requirement_id);

-- ---------------------------------------------------------------------------
-- Calendar events
-- ---------------------------------------------------------------------------

CREATE TABLE calendar_events (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title             text NOT NULL,
  starts_at         timestamptz NOT NULL,
  ends_at           timestamptz,
  recurrence_rule   text,                        -- RRULE, e.g. 'FREQ=WEEKLY;BYDAY=MO'
  meet_link         text,
  connection_id     uuid REFERENCES connections(id) ON DELETE SET NULL,
  external_event_id text,                        -- Google Calendar event id
  created_by        uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_project ON calendar_events(project_id);
CREATE INDEX idx_events_start ON calendar_events(starts_at);

CREATE TABLE calendar_event_attendees (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id    uuid NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
  member_id   uuid REFERENCES project_members(id) ON DELETE SET NULL,
  email       text
);
CREATE INDEX idx_evt_attendees_event ON calendar_event_attendees(event_id);

-- ---------------------------------------------------------------------------
-- Human-in-the-loop confirmation (the "ยืนยันก่อนทำจริง" flow)
-- ---------------------------------------------------------------------------

CREATE TABLE pending_confirmations (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  line_context_id uuid NOT NULL REFERENCES line_contexts(id) ON DELETE CASCADE,
  project_id      uuid REFERENCES projects(id) ON DELETE CASCADE,
  intent          text NOT NULL,                 -- 'create_task' | 'meeting_record' | 'calendar_event' ...
  draft_data      jsonb NOT NULL,                -- everything needed to execute on confirm
  status          confirmation_status NOT NULL DEFAULT 'pending',
  expires_at      timestamptz NOT NULL,          -- e.g. now() + interval '30 min'
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_pending_ctx ON pending_confirmations(line_context_id, status);

-- ---------------------------------------------------------------------------
-- Notifications / reminders
-- ---------------------------------------------------------------------------

CREATE TABLE notification_preferences (
  user_id          uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  enabled_types    jsonb NOT NULL DEFAULT '["due_soon","overdue","meeting_soon"]',
  quiet_hours_start time,
  quiet_hours_end   time,
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_notif_pref_updated BEFORE UPDATE ON notification_preferences
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Queue of reminders the scheduler will push to LINE. The worker selects rows
-- where scheduled_at <= now() AND sent_at IS NULL.
CREATE TABLE scheduled_notifications (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    uuid REFERENCES projects(id) ON DELETE CASCADE,
  target_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type          notification_type NOT NULL,
  ref_type      text,                            -- 'task' | 'calendar_event' | 'milestone'
  ref_id        uuid,
  payload       jsonb NOT NULL DEFAULT '{}',
  scheduled_at  timestamptz NOT NULL,
  sent_at       timestamptz,
  status        text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','skipped','failed')),
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_sched_due ON scheduled_notifications(scheduled_at) WHERE sent_at IS NULL;

-- ---------------------------------------------------------------------------
-- Audit log (ISO traceability of who did what)
-- ---------------------------------------------------------------------------

CREATE TABLE audit_log (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    uuid REFERENCES projects(id) ON DELETE SET NULL,
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  action        text NOT NULL,                   -- 'task.created', 'doc.issued', 'email.sent' ...
  entity_type   text,
  entity_id     uuid,
  detail        jsonb NOT NULL DEFAULT '{}',
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_project ON audit_log(project_id, created_at);

-- =============================================================================
-- End of schema
-- =============================================================================
