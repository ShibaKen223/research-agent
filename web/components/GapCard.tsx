import ReactMarkdown from "react-markdown";
import type { MarkdownItem } from "@/lib/markdown";

export function GapCard({ item }: { item: MarkdownItem }) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-5">
      <h3 className="mb-2 flex items-center gap-2 font-semibold text-foreground">
        <span className="text-teal">🕳️</span>
        {item.heading}
      </h3>
      <div className="prose-sm text-sm leading-relaxed text-muted [&_strong]:text-foreground">
        <ReactMarkdown>{item.body}</ReactMarkdown>
      </div>
    </div>
  );
}
