import { useEffect, useRef, useState } from "react";
import { Loader2, MessagesSquare, Send, Trash2 } from "lucide-react";
import { clearConversation, sendQuestion, useAskStore } from "../lib/askStore";

const SUGGESTIONS = [
  "How much did I spend on food last month?",
  "Which restaurant do I order from the most?",
  "When did I last buy fried chicken?",
  "Berapa total diskon yang saya dapat tahun ini?",
];

export default function AskPage() {
  const { messages, busy } = useAskStore();
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  function send(question: string) {
    if (!question.trim() || busy) return;
    setInput("");
    void sendQuestion(question);
  }

  return (
    <div className="mx-auto flex h-[calc(100dvh-5.5rem)] max-w-3xl flex-col md:h-[calc(100dvh-4rem)]">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Ask</h1>
          <p className="text-sm text-slate-500">Ask questions about your receipts in plain language.</p>
        </div>
        {messages.length > 0 && (
          <button className="btn-secondary px-3" onClick={clearConversation} disabled={busy}>
            <Trash2 size={16} /> Clear
          </button>
        )}
      </div>

      <div className="card flex flex-1 flex-col overflow-hidden">
        <div className="flex-1 space-y-4 overflow-y-auto p-4 md:p-6">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <MessagesSquare size={36} className="text-slate-300" />
              <p className="text-sm text-slate-500">Try one of these:</p>
              <div className="flex max-w-xl flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-full border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:border-brand-600 hover:text-brand-700"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="flex justify-end">
                <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-brand-900 px-4 py-2 text-sm text-white">
                  {m.text}
                </p>
              </div>
            ) : (
              <div key={i} className="max-w-[85%]">
                <p
                  className={`whitespace-pre-wrap rounded-2xl rounded-bl-sm px-4 py-2 text-sm ${
                    m.error ? "bg-red-50 text-red-700" : "bg-slate-100 text-slate-800"
                  }`}
                >
                  {m.text}
                </p>
              </div>
            ),
          )}

          {busy && (
            <p className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 size={16} className="animate-spin" /> Thinking…
            </p>
          )}
          <div ref={endRef} />
        </div>

        <form
          className="flex items-end gap-2 border-t border-slate-100 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <textarea
            className="input max-h-40 min-h-[42px] resize-none"
            rows={1}
            placeholder="Ask about your spending…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
          />
          <button type="submit" className="btn-primary h-[42px] px-3" disabled={!input.trim() || busy} aria-label="Send">
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
}
