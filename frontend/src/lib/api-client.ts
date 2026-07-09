/** Typed API client for Veritas backend */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export type PlanTier = "free" | "pro" | "team";
export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface User {
  id: string;
  email: string;
  full_name: string;
  plan: PlanTier;
  is_active: boolean;
  created_at: string;
  queries_today: number;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  owner_id: string;
  created_at: string;
  member_count: number;
  document_count: number;
}

export interface Document {
  id: string;
  workspace_id: string;
  filename: string;
  original_filename: string;
  content_type: string;
  doc_type: string;
  status: DocumentStatus;
  file_size: number;
  page_count: number;
  chunk_count: number;
  version: number;
  summary?: string | null;
  suggested_questions?: string[] | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  document_name: string;
  page_number?: number | null;
  heading?: string | null;
  snippet: string;
  score: number;
  citation_index: number;
}

export interface Message {
  id: string;
  thread_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[] | null;
  feedback?: string | null;
  created_at: string;
}

export interface Thread {
  id: string;
  workspace_id: string;
  title: string;
  is_shared: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface UsageStats {
  plan: PlanTier;
  queries_today: number;
  queries_limit: number;
  documents_count: number;
  documents_limit: number;
  workspaces_count: number;
  workspaces_limit: number;
  chunks_total: number;
}

export type WorkspaceRole = "owner" | "editor" | "viewer";

export interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: WorkspaceRole;
}

export interface Invitation {
  id: string;
  workspace_id: string;
  email: string;
  role: WorkspaceRole;
  status: string;
  expires_at: string;
  created_at: string;
  accepted_at?: string | null;
}

export interface ApiKey {
  id: string;
  workspace_id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  last_used_at?: string | null;
  expires_at?: string | null;
  created_at: string;
  secret?: string | null;
}

export interface Collection {
  id: string;
  workspace_id: string;
  name: string;
  description?: string | null;
  created_at: string;
  document_count: number;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body?: string | null;
  link_url?: string | null;
  read_at?: string | null;
  created_at: string;
}

export interface AuditLog {
  id: string;
  user_id?: string | null;
  workspace_id?: string | null;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  details?: Record<string, unknown> | null;
  created_at: string;
}

export interface IngestionJob {
  id: string;
  document_id: string;
  status: string;
  stage: string;
  error_message?: string | null;
  retry_count: number;
  created_at: string;
  finished_at?: string | null;
}

export interface DocumentVersion {
  id: string;
  document_id: string;
  version_number: number;
  is_active: boolean;
  file_size: number;
  content_hash?: string | null;
  change_note?: string | null;
  created_at: string;
}

export interface Entity {
  id: string;
  workspace_id: string;
  name: string;
  entity_type: string;
  normalized_name: string;
}

export interface Plan {
  id: string;
  code: PlanTier;
  name: string;
  description?: string | null;
  price_cents_monthly: number;
  queries_per_day: number;
  documents_limit: number;
  workspaces_limit: number;
  storage_bytes_limit: number;
  seats_limit: number;
}

export interface Invoice {
  id: string;
  stripe_invoice_id: string;
  status: string;
  amount_due_cents: number;
  amount_paid_cents: number;
  currency: string;
  hosted_invoice_url?: string | null;
  paid_at?: string | null;
  created_at: string;
}

export interface SharedLink {
  id: string;
  workspace_id: string;
  resource_type: string;
  resource_id: string;
  expires_at?: string | null;
  view_count: number;
  allow_download: boolean;
  created_at: string;
  token?: string | null;
}

export interface WebhookEndpoint {
  id: string;
  workspace_id: string;
  url: string;
  event_types: string[];
  is_active: boolean;
  description?: string | null;
  created_at: string;
}

export interface RetentionPolicy {
  id: string;
  workspace_id: string;
  resource_type: string;
  retain_days: number;
  hard_delete: boolean;
  is_active: boolean;
}

export interface ExportJob {
  id: string;
  job_type: string;
  status: string;
  download_url?: string | null;
  expires_at?: string | null;
  created_at: string;
  completed_at?: string | null;
}

export interface SsoConnection {
  id: string;
  workspace_id: string;
  provider: string;
  issuer_url?: string | null;
  client_id?: string | null;
  domains: string[];
  is_enforced: boolean;
  is_active: boolean;
}

class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("veritas_token");
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem("veritas_token", token);
  else localStorage.removeItem("veritas_token");
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    let message = res.statusText;
    let code: string | undefined;
    try {
      const data = await res.json();
      message = data?.error?.message || data?.detail || message;
      code = data?.error?.code;
    } catch {
      /* ignore */
    }
    throw new ApiError(message, res.status, code);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  register: (body: { email: string; password: string; full_name: string }) =>
    request<{ access_token: string; refresh_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  login: (body: { email: string; password: string }) =>
    request<{ access_token: string; refresh_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  me: () => request<User>("/auth/me"),

  listWorkspaces: () => request<Workspace[]>("/workspaces"),
  createWorkspace: (body: { name: string; description?: string }) =>
    request<Workspace>("/workspaces", { method: "POST", body: JSON.stringify(body) }),
  getWorkspace: (id: string) => request<Workspace>(`/workspaces/${id}`),

  listDocuments: (workspaceId: string) =>
    request<{ items: Document[]; total: number }>(
      `/workspaces/${workspaceId}/documents`,
    ),
  uploadDocument: async (workspaceId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Document>(`/workspaces/${workspaceId}/documents`, {
      method: "POST",
      body: form,
    });
  },
  deleteDocument: (workspaceId: string, documentId: string) =>
    request<{ ok: boolean }>(`/workspaces/${workspaceId}/documents/${documentId}`, {
      method: "DELETE",
    }),

  listThreads: (workspaceId: string) =>
    request<Thread[]>(`/workspaces/${workspaceId}/threads`),
  createThread: (workspaceId: string, title?: string) =>
    request<Thread>(`/workspaces/${workspaceId}/threads`, {
      method: "POST",
      body: JSON.stringify({ title: title || "New conversation" }),
    }),
  listMessages: (workspaceId: string, threadId: string) =>
    request<Message[]>(`/workspaces/${workspaceId}/threads/${threadId}/messages`),

  chat: (
    workspaceId: string,
    body: {
      question: string;
      thread_id?: string;
      document_ids?: string[];
      use_hyde?: boolean;
      use_rerank?: boolean;
    },
  ) =>
    request<{ thread_id: string; message: Message; citations: Citation[] }>(
      `/workspaces/${workspaceId}/chat`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  feedback: (
    workspaceId: string,
    threadId: string,
    messageId: string,
    feedback: "up" | "down",
  ) =>
    request<Message>(
      `/workspaces/${workspaceId}/threads/${threadId}/messages/${messageId}/feedback`,
      { method: "POST", body: JSON.stringify({ feedback }) },
    ),

  usage: () => request<UsageStats>("/billing/usage"),
  checkout: (plan: PlanTier) =>
    request<{ url: string; mock?: boolean }>("/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ plan }),
    }),
  listPlans: () => request<Plan[]>("/billing/plans"),
  listInvoices: () => request<Invoice[]>("/billing/invoices"),

  // Members & invitations
  listMembers: (workspaceId: string) =>
    request<Member[]>(`/workspaces/${workspaceId}/members`),
  inviteMember: (workspaceId: string, body: { email: string; role: WorkspaceRole }) =>
    request<Member | Invitation>(`/workspaces/${workspaceId}/members`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateMemberRole: (workspaceId: string, userId: string, role: WorkspaceRole) =>
    request<Member>(`/workspaces/${workspaceId}/members/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),
  removeMember: (workspaceId: string, userId: string) =>
    request<{ ok: boolean }>(`/workspaces/${workspaceId}/members/${userId}`, {
      method: "DELETE",
    }),
  listInvitations: (workspaceId: string) =>
    request<Invitation[]>(`/workspaces/${workspaceId}/invitations`),
  createInvitation: (
    workspaceId: string,
    body: { email: string; role: WorkspaceRole },
  ) =>
    request<Invitation>(`/workspaces/${workspaceId}/invitations`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  revokeInvitation: (workspaceId: string, invitationId: string) =>
    request<{ ok: boolean }>(
      `/workspaces/${workspaceId}/invitations/${invitationId}`,
      { method: "DELETE" },
    ),

  // API keys
  listApiKeys: (workspaceId: string) =>
    request<ApiKey[]>(`/workspaces/${workspaceId}/api-keys`),
  createApiKey: (
    workspaceId: string,
    body: { name: string; scopes?: string[] },
  ) =>
    request<ApiKey>(`/workspaces/${workspaceId}/api-keys`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  revokeApiKey: (workspaceId: string, keyId: string) =>
    request<{ ok: boolean }>(`/workspaces/${workspaceId}/api-keys/${keyId}`, {
      method: "DELETE",
    }),

  // Document extras
  documentStatus: (workspaceId: string, documentId: string) =>
    request<IngestionJob>(
      `/workspaces/${workspaceId}/documents/${documentId}/status`,
    ),
  documentVersions: (workspaceId: string, documentId: string) =>
    request<DocumentVersion[]>(
      `/workspaces/${workspaceId}/documents/${documentId}/versions`,
    ),
  documentEntities: (workspaceId: string, documentId: string) =>
    request<Entity[]>(
      `/workspaces/${workspaceId}/documents/${documentId}/entities`,
    ),
  reprocessDocument: (workspaceId: string, documentId: string) =>
    request<Document>(
      `/workspaces/${workspaceId}/documents/${documentId}/reprocess`,
      { method: "POST" },
    ),

  // Collections
  listCollections: (workspaceId: string) =>
    request<Collection[]>(`/workspaces/${workspaceId}/collections`),
  createCollection: (
    workspaceId: string,
    body: { name: string; description?: string; document_ids?: string[] },
  ) =>
    request<Collection>(`/workspaces/${workspaceId}/collections`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  addToCollection: (
    workspaceId: string,
    collectionId: string,
    documentId: string,
  ) =>
    request<Collection>(
      `/workspaces/${workspaceId}/collections/${collectionId}/documents`,
      { method: "POST", body: JSON.stringify({ document_id: documentId }) },
    ),
  removeFromCollection: (
    workspaceId: string,
    collectionId: string,
    documentId: string,
  ) =>
    request<{ ok: boolean }>(
      `/workspaces/${workspaceId}/collections/${collectionId}/documents/${documentId}`,
      { method: "DELETE" },
    ),

  // Notifications
  listNotifications: (unreadOnly = false) =>
    request<Notification[]>(
      `/notifications?unread_only=${unreadOnly ? "true" : "false"}`,
    ),
  markNotificationRead: (id: string) =>
    request<Notification>(`/notifications/${id}/read`, { method: "POST" }),
  markAllNotificationsRead: () =>
    request<{ ok: boolean; marked: number }>("/notifications/read-all", {
      method: "POST",
    }),

  // Audit
  listAuditLogs: (workspaceId: string) =>
    request<AuditLog[]>(`/workspaces/${workspaceId}/audit-logs`),

  // Shared links & webhooks
  listSharedLinks: (workspaceId: string) =>
    request<SharedLink[]>(`/workspaces/${workspaceId}/shared-links`),
  createSharedLink: (
    workspaceId: string,
    body: {
      resource_type: "thread" | "document" | "collection";
      resource_id: string;
      expires_at?: string;
      allow_download?: boolean;
    },
  ) =>
    request<SharedLink>(`/workspaces/${workspaceId}/shared-links`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  revokeSharedLink: (workspaceId: string, linkId: string) =>
    request<{ ok: boolean }>(
      `/workspaces/${workspaceId}/shared-links/${linkId}`,
      { method: "DELETE" },
    ),
  listWebhooks: (workspaceId: string) =>
    request<WebhookEndpoint[]>(`/workspaces/${workspaceId}/webhooks`),
  createWebhook: (
    workspaceId: string,
    body: { url: string; event_types: string[]; description?: string },
  ) =>
    request<WebhookEndpoint>(`/workspaces/${workspaceId}/webhooks`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteWebhook: (workspaceId: string, endpointId: string) =>
    request<{ ok: boolean }>(
      `/workspaces/${workspaceId}/webhooks/${endpointId}`,
      { method: "DELETE" },
    ),

  // Compliance
  listRetentionPolicies: (workspaceId: string) =>
    request<RetentionPolicy[]>(
      `/workspaces/${workspaceId}/retention-policies`,
    ),
  upsertRetentionPolicy: (
    workspaceId: string,
    body: {
      resource_type: string;
      retain_days: number;
      hard_delete?: boolean;
      notes?: string;
    },
  ) =>
    request<RetentionPolicy>(`/workspaces/${workspaceId}/retention-policies`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  createExportJob: (body: {
    job_type?: "gdpr_user_export" | "workspace_export";
    workspace_id?: string;
  }) =>
    request<ExportJob>("/exports", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listExportJobs: () => request<ExportJob[]>("/exports"),
  listSsoConnections: (workspaceId: string) =>
    request<SsoConnection[]>(`/workspaces/${workspaceId}/sso`),
  upsertSsoConnection: (
    workspaceId: string,
    body: {
      provider: string;
      issuer_url?: string;
      client_id?: string;
      client_secret?: string;
      domains?: string[];
      is_enforced?: boolean;
    },
  ) =>
    request<SsoConnection>(`/workspaces/${workspaceId}/sso`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};

export { ApiError, API_BASE };

/** SSE streaming chat helper */
export async function streamChat(
  workspaceId: string,
  body: {
    question: string;
    thread_id?: string;
    document_ids?: string[];
    use_hyde?: boolean;
    use_rerank?: boolean;
  },
  handlers: {
    onThread?: (threadId: string) => void;
    onCitations?: (citations: Citation[]) => void;
    onToken?: (token: string) => void;
    onDone?: (data: {
      answer: string;
      citations: Citation[];
      latency_ms: number;
    }) => void;
    onMessage?: (data: { message_id: string; thread_id: string }) => void;
    onError?: (err: Error) => void;
  },
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/workspaces/${workspaceId}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });

  if (!res.ok || !res.body) {
    let message = "Stream failed";
    try {
      const data = await res.json();
      message = data?.error?.message || message;
    } catch {
      /* ignore */
    }
    throw new ApiError(message, res.status);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const lines = part.split("\n");
      let event = "message";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (!data) continue;
      try {
        const parsed = JSON.parse(data);
        if (event === "thread") handlers.onThread?.(parsed.thread_id);
        if (event === "citations") handlers.onCitations?.(parsed.citations);
        if (event === "token") handlers.onToken?.(parsed.token);
        if (event === "done") handlers.onDone?.(parsed);
        if (event === "message") handlers.onMessage?.(parsed);
      } catch (err) {
        handlers.onError?.(err as Error);
      }
    }
  }
}
