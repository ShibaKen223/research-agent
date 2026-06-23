import ReactMarkdown from "react-markdown";
import type { MarkdownItem } from "@/lib/markdown";

export function GapCard({ item }: { item: MarkdownItem }) {
  return (
    <div className="hover-glow rounded-2xl border border-border bg-surface p-5 transition-all duration-200 hover:border-border-hover">
      <h3 className="mb-2 flex items-center gap-2 font-semibold text-foreground">
        <span className="h-2 w-2 shrink-0 rounded-full bg-accent" />
        {item.heading}
      </h3>
      <div className="prose-sm text-sm leading-relaxed text-muted [&_strong]:text-foreground">
        <ReactMarkdown>{item.body}</ReactMarkdown>
      </div>
    </div>
  );
}
