import { useSyncExternalStore } from "react";
import { api, errorMessage } from "../api";
import type { UploadResponse } from "../types";

// The running extraction lives here, outside any page, so the user can navigate
// while the model reads the receipt. One receipt at a time: the model runs on CPU
// and a second upload would only queue behind the first. When it finishes, the
// receipts table reloads and a one-off popup (ExtractNotice) appears on any page.

export type ExtractJob =
  | { status: "running"; fileName: string }
  | { status: "done"; fileName: string; upload: UploadResponse; file: File }
  | { status: "error"; fileName: string; error: string };

interface ExtractState {
  job: ExtractJob | null;
  /** Bumped after every successful extraction, so the receipts table can reload. */
  completed: number;
}

let state: ExtractState = { job: null, completed: 0 };
const listeners = new Set<() => void>();

function update(next: Partial<ExtractState>) {
  state = { ...state, ...next };
  listeners.forEach((notify) => notify());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useExtractStore(): ExtractState {
  return useSyncExternalStore(subscribe, () => state);
}

export const isExtracting = (s: ExtractState) => s.job?.status === "running";

export async function startExtraction(file: File) {
  if (isExtracting(state)) return;
  update({ job: { status: "running", fileName: file.name } });
  try {
    const upload = await api.upload(file);
    update({
      job: { status: "done", fileName: file.name, upload, file },
      completed: state.completed + 1,
    });
  } catch (e) {
    update({ job: { status: "error", fileName: file.name, error: errorMessage(e) } });
  }
}

/** Close the finished/failed popup. A running job can't be dismissed. */
export function dismissExtraction() {
  if (!isExtracting(state)) update({ job: null });
}
