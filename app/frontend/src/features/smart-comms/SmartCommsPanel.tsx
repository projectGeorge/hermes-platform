import { useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

import { useConversationMessages, useDeleteConversation, useResolveConversation, useStreamMessage, type SmartCommsContextType } from "./api";

type SmartCommsPanelProps = {
  contextType: SmartCommsContextType;
  contextId: string | undefined;
  routePath: string;
  label: string;
};

const MIN_W = 320;
const MAX_W = 800;
const MIN_H = 280;

// ─── Resize handle ────────────────────────────────────────────────────────────

type ResizeAxis = "w" | "h" | "wh";

function useResizePanel(initialW: number, initialH: number) {
  const [size, setSize] = useState({ w: initialW, h: initialH });

  const startResize = useCallback(
    (axis: ResizeAxis) => (e: React.MouseEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startY = e.clientY;
      const startW = size.w;
      const startH = size.h;
      const maxH = Math.round(window.innerHeight * 0.92);

      function onMove(ev: MouseEvent) {
        const dx = startX - ev.clientX; // drag left → wider
        const dy = startY - ev.clientY; // drag up   → taller
        setSize({
          w: axis === "h" ? startW : Math.min(MAX_W, Math.max(MIN_W, startW + dx)),
          h: axis === "w" ? startH : Math.min(maxH, Math.max(MIN_H, startH + dy)),
        });
      }

      function onUp() {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      }

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [size.w, size.h],
  );

  return { size, startResize };
}

// ─── Component ────────────────────────────────────────────────────────────────

export function SmartCommsPanel({ contextType, contextId, routePath, label }: SmartCommsPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const { size, startResize } = useResizePanel(384, 520);

  // Close on outside click
  useEffect(() => {
    if (!isExpanded) return;
    function handleOutside(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setIsExpanded(false);
      }
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [isExpanded]);

  const { data: conversation } = useResolveConversation(contextType, routePath, contextId, isExpanded);
  const { data: messageHistory } = useConversationMessages(conversation?.id, isExpanded);
  const streamMutation = useStreamMessage(conversation?.id);
  const deleteConversationMutation = useDeleteConversation();

  const [streamingDraft, setStreamingDraft] = useState<string | null>(null);
  const [pendingUserMessage, setPendingUserMessage] = useState<string | null>(null);
  const prevMsgCount = useRef(0);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || streamMutation.isPending) return;

    setInput("");
    setPendingUserMessage(trimmed);
    setStreamingDraft("");
    streamMutation.mutate({
      content: trimmed,
      onChunk: (chunk: string) => {
        setStreamingDraft((prev) => (prev ?? "") + chunk);
      },
    });
  }, [input, streamMutation]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messageHistory, streamingDraft, streamMutation.isPending]);

  useEffect(() => {
    setInput("");
    setStreamingDraft(null);
    setPendingUserMessage(null);
    prevMsgCount.current = 0;
  }, [conversation?.id]);

  useEffect(() => {
    const count = messageHistory?.length ?? 0;
    if (count > prevMsgCount.current && !streamMutation.isPending) {
      setStreamingDraft(null);
      setPendingUserMessage(null);
    }
    prevMsgCount.current = count;
  }, [messageHistory, streamMutation.isPending]);

  // ── Collapsed trigger ──────────────────────────────────────────────────────

  if (!isExpanded) {
    return (
      <button
        onClick={() => setIsExpanded(true)}
        className="fixed bottom-6 right-6 z-[9999] flex h-14 w-14 items-center justify-center rounded-full border border-amber-400/25 bg-[rgba(19,19,24,0.97)] text-amber-300 shadow-lg shadow-black/40 transition-all duration-200 hover:scale-110 hover:border-amber-400/45 hover:bg-[rgba(24,24,31,0.99)] hover:shadow-[0_0_28px_rgba(251,191,36,0.18)]"
        aria-label="Open Smart Comms"
        title="Smart Comms"
      >
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24">
          <path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
        </svg>
      </button>
    );
  }

  // ── Expanded panel ─────────────────────────────────────────────────────────

  return (
    <div
      ref={panelRef}
      className="fixed bottom-6 right-6 z-[9999] flex flex-col rounded-[1.5rem] border border-[var(--hermes-border)] bg-[rgba(12,12,16,0.98)] shadow-2xl shadow-black/50"
      style={{ width: size.w, height: size.h }}
    >
      {/* ── Top resize edge */}
      <div
        className="absolute inset-x-0 top-0 h-1.5 cursor-ns-resize rounded-t-[1.5rem]"
        onMouseDown={startResize("h")}
      />

      {/* ── Left resize edge */}
      <div
        className="absolute inset-y-0 left-0 w-1.5 cursor-ew-resize rounded-l-[1.5rem]"
        onMouseDown={startResize("w")}
      />

      {/* ── Top-left corner grip (resize both axes) */}
      <div
        className="absolute left-0 top-0 z-10 flex h-8 w-8 cursor-nwse-resize items-start justify-start rounded-tl-[1.5rem] p-2"
        onMouseDown={startResize("wh")}
      >
        <svg className="text-white/20" fill="currentColor" viewBox="0 0 8 8" width="8" height="8">
          <circle cx="1.5" cy="1.5" r="1" />
          <circle cx="5"   cy="1.5" r="1" />
          <circle cx="1.5" cy="5"   r="1" />
          <circle cx="5"   cy="5"   r="1" />
        </svg>
      </div>

      {/* ── Header */}
      <div className="flex items-center justify-between border-b border-white/8 px-4 py-3 shrink-0">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-[0.22em] text-amber-400">Smart Comms</p>
          <p className="truncate text-sm text-slate-400">{label}</p>
        </div>
        <div className="ml-2 flex items-center gap-1">
          {conversation && messageHistory && messageHistory.length > 0 ? (
            <button
              onClick={() => {
                deleteConversationMutation.mutate(conversation.id);
              }}
              className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/10 text-slate-400 transition-colors hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-400"
              aria-label="Clear conversation"
              title="Clear conversation"
              disabled={deleteConversationMutation.isPending}
            >
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                <path d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          ) : null}
          <button
            onClick={() => setIsExpanded(false)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/10 text-slate-400 hover:text-white"
            aria-label="Close Smart Comms"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24">
              <path d="M6 18L18 6M6 6l12 12" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
            </svg>
          </button>
        </div>
      </div>

      {/* ── Message history */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
        {messageHistory && messageHistory.length > 0 ? (
          messageHistory.map((msg) => (
            <div
              key={msg.id}
              className={msg.role === "user" ? "flex justify-end" : "flex justify-start"}
            >
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                  msg.role === "user"
                    ? "bg-amber-400/10 border border-amber-400/20 text-slate-200"
                    : "bg-white/[0.03] border border-white/5 text-slate-300 prose prose-invert prose-sm max-w-none"
                }`}
              >
                {msg.role === "assistant" ? (
                  <Markdown>{msg.content}</Markdown>
                ) : (
                  <p>{msg.content}</p>
                )}
              </div>
            </div>
          ))
        ) : (
          <p className="text-sm text-slate-500 italic">
            Ask a question about the current page context.
          </p>
        )}

        {pendingUserMessage !== null && (
          <div className="flex justify-end">
            <div className="max-w-[85%] rounded-xl px-3 py-2 text-sm bg-amber-400/10 border border-amber-400/20 text-slate-200">
              <p>{pendingUserMessage}</p>
            </div>
          </div>
        )}

        {streamingDraft !== null && streamingDraft.length > 0 && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-xl px-3 py-2 text-sm bg-white/[0.03] border border-white/5 text-slate-300 prose prose-invert prose-sm max-w-none">
              <Markdown>{streamingDraft}</Markdown>
            </div>
          </div>
        )}

        {streamMutation.isPending ? (
          <p className="text-sm text-amber-400 animate-pulse">Thinking...</p>
        ) : null}
      </div>

      {/* ── Input bar */}
      <div className="border-t border-white/8 p-3 shrink-0">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this page..."
            rows={2}
            className="flex-1 resize-none rounded-xl border border-white/10 bg-[rgba(7,7,10,0.92)] px-3 py-2 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-amber-400/40"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || streamMutation.isPending}
            className="self-end rounded-xl border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-sm font-medium text-amber-200 transition hover:border-amber-400/45 hover:bg-amber-400/20 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
