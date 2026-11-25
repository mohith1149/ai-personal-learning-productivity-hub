import { Fragment, type ReactNode } from "react";

/** A deliberately small, SAFE markdown renderer for assistant replies: paragraphs, headings, bullet and numbered lists, **bold**, `code` and
 *  fenced code. It builds React elements (never raw HTML), so nothing the model writes can inject markup, and links are shown as plain text. */

const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g;

function inline(text: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2)
      return (
        <code key={i} className="rounded bg-slate-200/70 px-1 py-0.5 text-[0.85em] dark:bg-slate-700/70">
          {part.slice(1, -1)}
        </code>
      );
    return <Fragment key={i}>{part}</Fragment>;
  });
}

type Block = { kind: "p"; text: string } | { kind: "h"; text: string } | { kind: "ul"; items: string[] } | { kind: "ol"; items: string[] } | { kind: "code"; text: string };

export function parseBlocks(source: string): Block[] {
  const blocks: Block[] = [];
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  let para: string[] = [];
  const flush = () => {
    if (para.length) blocks.push({ kind: "p", text: para.join("\n") });
    para = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim().startsWith("```")) {
      flush();
      const code: string[] = [];
      for (i++; i < lines.length && !lines[i].trim().startsWith("```"); i++) code.push(lines[i]);
      blocks.push({ kind: "code", text: code.join("\n") });
      continue;
    }
    const heading = line.match(/^\s{0,3}#{1,6}\s+(.*)$/);
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (heading) {
      flush();
      blocks.push({ kind: "h", text: heading[1] });
    } else if (bullet || numbered) {
      flush();
      const kind: "ul" | "ol" = bullet ? "ul" : "ol";
      const last = blocks[blocks.length - 1];
      const text = (bullet ?? numbered)![1];
      if (last && last.kind === kind) last.items.push(text);
      else blocks.push(kind === "ul" ? { kind, items: [text] } : { kind, items: [text] });
    } else if (!line.trim()) {
      flush();
    } else {
      para.push(line);
    }
  }
  flush();
  return blocks;
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      {parseBlocks(text).map((b, i) => {
        if (b.kind === "h") return <p key={i} className="font-semibold">{inline(b.text)}</p>;
        if (b.kind === "ul") return <ul key={i} className="list-disc space-y-0.5 pl-5">{b.items.map((t, j) => <li key={j}>{inline(t)}</li>)}</ul>;
        if (b.kind === "ol") return <ol key={i} className="list-decimal space-y-0.5 pl-5">{b.items.map((t, j) => <li key={j}>{inline(t)}</li>)}</ol>;
        if (b.kind === "code") return <pre key={i} className="overflow-x-auto rounded-lg bg-slate-200/70 p-2 text-xs dark:bg-slate-700/70"><code>{b.text}</code></pre>;
        return <p key={i} className="whitespace-pre-wrap">{inline(b.text)}</p>;
      })}
    </div>
  );
}
