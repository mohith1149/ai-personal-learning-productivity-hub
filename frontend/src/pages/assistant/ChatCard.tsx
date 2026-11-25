import { Bot, Plus, SendHorizontal, Sparkles } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useChat, useConversation } from "../../api/assistant";
import { controlClass } from "../../components/forms";
import { Markdown } from "../../components/Markdown";
import { Button, Card, cx, Spinner } from "../../components/ui";
import { ModelPicker } from "./ModelPicker";

const SUGGESTIONS = ["What is on my plan today?", "What is overdue?", "How is my roadmap going?", "What should I work on next?"];

/** "get_today_tasks" -> "today tasks" */
const friendly = (tool: string) => tool.replace(/^get_/, "").replace(/_/g, " ");

function Avatar() {
  return (
    <span aria-hidden className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-400">
      <Bot className="h-4 w-4" />
    </span>
  );
}

function Typing() {
  return (
    <div role="status" aria-label="Thinking" className="flex items-start gap-2.5">
      <Avatar />
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm bg-slate-100 px-4 py-3 dark:bg-slate-800">
        {[0, 150, 300].map((d) => (
          <span key={d} className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: `${d}ms` }} />
        ))}
        <span className="sr-only">Thinking…</span>
      </div>
    </div>
  );
}

/** The chat window. Only shown when a provider is configured. Anything the assistant wants to change appears in "Waiting for your approval". */
export function ChatCard() {
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState<string | null>(null); // shown as your bubble while the answer is on its way
  const [proposed, setProposed] = useState(0);
  const convo = useConversation(conversationId);
  const chat = useChat();
  const end = useRef<HTMLDivElement>(null);
  const messages = convo.data?.messages ?? [];

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [messages.length, chat.isPending]);

  const send = (override?: string) => {
    const message = (override ?? text).trim();
    if (!message || chat.isPending) return;
    setSending(message);
    setProposed(0);
    chat.mutate(
      { message, conversation_id: conversationId },
      {
        onSuccess: (r) => {
          setText("");
          setConversationId(r.conversation_id);
          setProposed(r.pending.length);
        },
        onSettled: () => setSending(null),
      },
    );
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  const empty = messages.length === 0 && !chat.isPending && !convo.isLoading && !sending;

  return (
    <Card aria-label="Chat" className="flex flex-col gap-3 !p-0">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-5 py-3 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-brand-600 dark:text-brand-400" aria-hidden />
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Chat</h2>
        </div>
        <div className="flex items-center gap-2">
          <ModelPicker />
          {conversationId !== null && (
            <Button
              variant="ghost"
              icon={Plus}
              className="px-2.5 py-1.5 text-xs"
              onClick={() => {
                setConversationId(null);
                setProposed(0);
                setSending(null);
                chat.reset();
              }}
            >
              New chat
            </Button>
          )}
        </div>
      </div>

      <div role="log" aria-label="Conversation" aria-live="polite" className="flex h-[26rem] flex-col gap-4 overflow-y-auto px-5 py-2 sm:h-[30rem]">
        {convo.isLoading && <Spinner />}
        {empty && (
          <div className="m-auto max-w-md text-center">
            <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-400">
              <Bot className="h-6 w-6" aria-hidden />
            </span>
            <p className="mt-3 text-sm font-medium text-slate-900 dark:text-white">How can I help?</p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              I look things up in your plan, courses, projects and habits. I can&apos;t change anything myself: anything I suggest waits for your approval.
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => send(s)}
                  className="rounded-full border border-slate-200 px-3 py-1.5 text-xs text-slate-700 transition hover:border-brand-500 hover:bg-brand-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="flex justify-end">
              <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-brand-600 px-4 py-2.5 text-sm text-white">{m.text}</p>
            </div>
          ) : (
            m.text || m.tool_calls.length > 0 ? (
              <div key={m.id} className="flex items-start gap-2.5">
                <Avatar />
                <div className="min-w-0 max-w-[88%]">
                  {m.tool_calls.length > 0 && (
                    <p className="mb-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                      <span>Looked up:</span>
                      {m.tool_calls.map((t, i) => (
                        <span key={i} className="rounded-full bg-slate-100 px-2 py-0.5 dark:bg-slate-800">
                          {friendly(t.name)}
                        </span>
                      ))}
                    </p>
                  )}
                  {m.text && (
                    <div className="rounded-2xl rounded-tl-sm bg-slate-100 px-4 py-2.5 text-slate-900 dark:bg-slate-800 dark:text-slate-100">
                      <Markdown text={m.text} />
                    </div>
                  )}
                </div>
              </div>
            ) : null
          ),
        )}
        {sending && (
          <div className="flex justify-end">
            <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-brand-600/80 px-4 py-2.5 text-sm text-white">{sending}</p>
          </div>
        )}
        {chat.isPending && <Typing />}
        <div ref={end} />
      </div>

      {proposed > 0 && !chat.isPending && (
        <p role="status" className="mx-5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          The assistant proposed {proposed} change{proposed === 1 ? "" : "s"}. Nothing has changed yet. Review {proposed === 1 ? "it" : "them"} under &quot;Waiting for your approval&quot;.
        </p>
      )}
      {(convo.error || chat.error) && (
        <p role="alert" className="mx-5 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300">
          {(chat.error ?? convo.error)?.message}
        </p>
      )}

      <form
        className="flex items-end gap-2 border-t border-slate-200 p-3 dark:border-slate-800"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <textarea
          aria-label="Message"
          rows={1}
          value={text}
          maxLength={4000}
          placeholder="Ask about your plan, progress or what to do next…"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          className={cx(controlClass, "max-h-32 min-h-[2.5rem] flex-1 resize-none")}
        />
        <Button type="submit" icon={SendHorizontal} loading={chat.isPending} disabled={!text.trim()} aria-label="Send" className="h-10">
          <span className="hidden sm:inline">Send</span>
        </Button>
      </form>
      <p className="-mt-2 px-5 pb-3 text-[11px] text-slate-400">Enter to send · Shift+Enter for a new line · AI can be wrong, check before you rely on it.</p>
    </Card>
  );
}
