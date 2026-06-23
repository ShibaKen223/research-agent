import ReactMarkdown from "react-markdown";
import type { MarkdownItem } from "@/lib/markdown";

export function TrendCard({ item, index }: { item: MarkdownItem; index: number }) {
  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-accent text-sm font-semibold text-accent">
          {index + 1}
        </span>
        <span className="mt-1 w-px flex-1 bg-border" />
      </div>
      <div className="flex-1 pb-6">
        <h3 className="mb-2 font-semibold text-foreground">{item.heading}</h3>
        <div className="prose-sm text-sm leading-relaxed text-muted [&_strong]:text-foreground">
          <ReactMarkdown>{item.body}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
