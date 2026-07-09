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
