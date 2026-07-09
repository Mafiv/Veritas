"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Citation, Message, User, Workspace } from "@/lib/api-client";

interface AppState {
  user: User | null;
  workspace: Workspace | null;
  workspaces: Workspace[];
  setUser: (user: User | null) => void;
  setWorkspace: (workspace: Workspace | null) => void;
  setWorkspaces: (workspaces: Workspace[]) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      user: null,
      workspace: null,
      workspaces: [],
      setUser: (user) => set({ user }),
      setWorkspace: (workspace) => set({ workspace }),
      setWorkspaces: (workspaces) => set({ workspaces }),
    }),
    { name: "veritas-app" },
  ),
);

export interface ChatMessageLocal extends Omit<Message, "id" | "created_at"> {
  id: string;
  created_at: string;
  streaming?: boolean;
}

interface ChatState {
  messages: ChatMessageLocal[];
  citations: Citation[];
  threadId: string | null;
  isStreaming: boolean;
  setMessages: (messages: ChatMessageLocal[]) => void;
  appendMessage: (message: ChatMessageLocal) => void;
  updateLastAssistant: (patch: Partial<ChatMessageLocal>) => void;
  setCitations: (citations: Citation[]) => void;
  setThreadId: (id: string | null) => void;
  setStreaming: (v: boolean) => void;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  citations: [],
  threadId: null,
  isStreaming: false,
  setMessages: (messages) => set({ messages }),
  appendMessage: (message) =>
    set((s) => ({ messages: [...s.messages, message] })),
  updateLastAssistant: (patch) =>
    set((s) => {
      const messages = [...s.messages];
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === "assistant") {
          messages[i] = { ...messages[i], ...patch };
          break;
        }
      }
      return { messages };
    }),
  setCitations: (citations) => set({ citations }),
  setThreadId: (threadId) => set({ threadId }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  reset: () =>
    set({ messages: [], citations: [], threadId: null, isStreaming: false }),
}));
