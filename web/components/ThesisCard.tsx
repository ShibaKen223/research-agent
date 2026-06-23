"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { MarkdownItem } from "@/lib/markdown";

function storageKey(filename: string, heading: string) {
  return `research-agent:bookmark:${filename}:${heading}`;
}

export function ThesisCard({ item, filename }: { item: MarkdownItem; filename: string }) {
  const key = storageKey(filename, item.heading);
  const [bookmarked, setBookmarked] = useState(false);

  useEffect(() => {
    setBookmarked(localStorage.getItem(key) === "1");
  }, [key]);

  const toggle = () => {
    const next = !bookmarked;
    setBookmarked(next);
    if (next) localStorage.setItem(key, "1");
    else localStorage.removeItem(key);
  };

  return (
    <div className="relative rounded-2xl border border-border bg-surface p-5">
      <button
        onClick={toggle}
        aria-label="收藏"
        className={`absolute right-4 top-4 text-xl transition ${
          bookmarked ? "text-accent" : "text-muted hover:text-accent"
        }`}
      >
        {bookmarked ? "★" : "☆"}
      </button>
      <h3 className="mb-2 flex items-center gap-2 pr-8 font-semibold text-foreground">
        <span className="text-accent">🎓</span>
        {item.heading}
      </h3>
      <div className="prose-sm text-sm leading-relaxed text-muted [&_strong]:text-foreground [&_blockquote]:border-l-2 [&_blockquote]:border-accent [&_blockquote]:pl-3 [&_blockquote]:text-foreground/80">
        <ReactMarkdown>{item.body}</ReactMarkdown>
      </div>
    </div>
  );
}
