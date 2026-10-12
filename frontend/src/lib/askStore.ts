import { useSyncExternalStore } from "react";
import { api, errorMessage } from "../api";
import type { ToolCall } from "../types";

// The Ask conversation lives here, outside the page component, so a pending /ask
// survives navigating to another page: its answer is stored when it arrives and
// shown when the user comes back. (A reload still loses a pending answer.)

export interface Message {
  role: "user" | "assistant";
  text: string;
  toolCalls?: ToolCall[];
  error?: boolean;
}

interface AskState {
  messages: Message[];
  busy: boolean;
}

const STORAGE_KEY = "ask-history";

function loadHistory(): Message[] {
  try {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    return saved ? (JSON.parse(saved) as Message[]) : [];
  } catch {
    return [];
  }
}

let state: AskState = { messages: loadHistory(), busy: false };
const listeners = new Set<() => void>();

function update(next: Partial<AskState>) {
  state = { ...state, ...next };
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state.messages));
  } catch {
    /* storage unavailable: history just won't survive a reload */
  }
  listeners.forEach((notify) => notify());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useAskStore(): AskState {
  return useSyncExternalStore(subscribe, () => state);
}

export async function sendQuestion(question: string) {
  const q = question.trim();
  if (!q || state.busy) return;
  update({ messages: [...state.messages, { role: "user", text: q }], busy: true });
  let reply: Message;
  try {
    const res = await api.ask(q);
    reply = { role: "assistant", text: res.answer, toolCalls: res.tool_calls };
  } catch (e) {
    reply = { role: "assistant", text: errorMessage(e), error: true };
  }
  update({ messages: [...state.messages, reply], busy: false });
}

export function clearConversation() {
  if (!state.busy) update({ messages: [] });
}
