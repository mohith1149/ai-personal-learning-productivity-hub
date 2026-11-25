import { Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useChat, useConversation } from "../../api/assistant";
import { FormError, TextArea } from "../../components/forms";
import { Button, Card, ErrorNotice, Spinner } from "../../components/ui";

/** The chat window. Only shown when a provider is configured. Anything the assistant wants to change appears in "Waiting for your approval". */
export function ChatCard() {
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [proposed, setProposed] = useState(0);
  const convo = useConversation(conversationId);
  const chat = useChat();
  const end = useRef<HTMLDivElement>(null);
  const messages = convo.data?.messages ?? [];

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, chat.isPending]);

  const send = () => {
    const message = text.trim();
    if (!message || chat.isPending) return;
    chat.mutate(
      { message, conversation_id: conversationId },
      {
        onSuccess: (r) => {
          setText("");
          setConversationId(r.conversation_id);
          setProposed(r.pending.length);
        },
      },
    );
  };

  return (
    <Card aria-label="Chat">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Chat</h2>
        {conversationId !== null && (
          <Button
            variant="ghost"
            onClick={() => {
              setConversationId(null);
              setProposed(0);
              chat.reset();
            }}
          >
            New chat
          </Button>
        )}
      </div>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        Ask about your plan, progress or what to do next. The assistant looks things up in your data. It can&apos;t change anything itself: its suggestions appear below for you to approve.
      </p>
      <div role="log" aria-label="Conversation" className="mt-3 max-h-96 space-y-3 overflow-y-auto">
        {convo.isLoading && <Spinner />}
        {messages.length === 0 && !chat.isPending && !convo.isLoading && <p className="text-sm text-slate-500 dark:text-slate-400">No messages yet.</p>}
        {messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "ml-8 rounded-lg bg-brand-50 px-3 py-2 dark:bg-slate-800" : "mr-8 rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700"}>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{m.role === "user" ? "You" : "Assistant"}</p>
            {m.text && <p className="whitespace-pre-wrap text-sm text-slate-900 dark:text-slate-100">{m.text}</p>}
            {m.tool_calls.length > 0 && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Looked up: {m.tool_calls.map((t) => t.name).join(", ")}</p>}
          </div>
        ))}
        {chat.isPending && <Spinner label="Thinking…" />}
        <div ref={end} />
      </div>
      {proposed > 0 && !chat.isPending && (
        <p role="status" className="mt-2 text-sm text-slate-700 dark:text-slate-300">
          The assistant proposed {proposed} change{proposed === 1 ? "" : "s"}. Nothing has changed yet. Review {proposed === 1 ? "it" : "them"} under &quot;Waiting for your approval&quot;.
        </p>
      )}
      {convo.error && <ErrorNotice error={convo.error} />}
      <FormError message={chat.error?.message} />
      <form
        className="mt-3 space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <TextArea label="Message" rows={2} value={text} maxLength={4000} onChange={(e) => setText(e.target.value)} />
        <Button type="submit" icon={Send} loading={chat.isPending} disabled={!text.trim()}>
          Send
        </Button>
      </form>
    </Card>
  );
}
