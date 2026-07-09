# Alembic migrations

Domain-grouped revisions (reviewable / independently revertible):

| Rev | Domain |
|-----|--------|
| `001_identity` | users, workspaces, members, invitations, refresh_tokens, api_keys |
| `002_documents` | documents, versions, chunks, summaries, permissions, collections, ingestion_jobs |
| `003_knowledge_graph` | entities, document_entities, entity_relationships |
| `004_chat` | threads, messages, citations, feedback, comments |
| `005_billing` | plans, subscriptions, usage_events, usage_meters, invoices |
| `006_audit_notifications` | audit_logs, login_history, notifications |
| `007_enterprise` | webhooks, SSO, retention, export_jobs, shared_links |

```bash
cd backend
alembic upgrade head
alembic downgrade -1   # revert one domain
```

Full documentation: [`docs/SCHEMA.md`](../../../docs/SCHEMA.md).
