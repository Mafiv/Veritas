-- Repair legacy create_all enum types to match Alembic / SQLAlchemy model names.
-- Safe for dev DBs created before migrations were applied.

BEGIN;

-- users.plan: plantier -> plan_tier
ALTER TABLE users ALTER COLUMN plan DROP DEFAULT;
ALTER TABLE users
  ALTER COLUMN plan TYPE plan_tier
  USING plan::text::plan_tier;
ALTER TABLE users ALTER COLUMN plan SET DEFAULT 'FREE'::plan_tier;

DROP TYPE IF EXISTS plantier;

-- workspace_members.role: workspacerole -> workspace_role
ALTER TABLE workspace_members
  ALTER COLUMN role TYPE workspace_role
  USING role::text::workspace_role;

DROP TYPE IF EXISTS workspacerole;

-- documents: legacy enum names -> migration enum names
ALTER TABLE documents
  ALTER COLUMN doc_type TYPE document_type
  USING doc_type::text::document_type;

ALTER TABLE documents
  ALTER COLUMN status TYPE document_status
  USING status::text::document_status;

DROP TYPE IF EXISTS documenttype;
DROP TYPE IF EXISTS documentstatus;

-- Soft-delete columns missing from early create_all schema
ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_workspaces_deleted_at ON workspaces (deleted_at);

ALTER TABLE chat_threads ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_chat_threads_deleted_at ON chat_threads (deleted_at);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_documents_deleted_at ON documents (deleted_at);

COMMIT;
