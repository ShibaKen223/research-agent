"use client";

import { useState } from "react";

type Props = {
  onSearch: (keyword: string, limit: number) => void;
  disabled?: boolean;
};

export function SearchBar({ onSearch, disabled }: Props) {
  const [keyword, setKeyword] = useState("");
  const [limit, setLimit] = useState(20);

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (keyword.trim()) onSearch(keyword.trim(), limit);
      }}
    >
      <div className="flex items-center gap-4">
        <input
          className="flex-1 border-b-2 border-foreground bg-transparent pb-3 text-2xl text-foreground outline-none placeholder:text-muted/50 focus:border-accent"
          placeholder="輸入研究關鍵字"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          disabled={disabled}
        />
        <button
          type="submit"
          disabled={disabled || !keyword.trim()}
          className="shrink-0 rounded-full bg-accent px-8 py-3 text-sm font-medium text-accent-foreground transition hover:opacity-90 disabled:opacity-30"
        >
          搜尋
        </button>
      </div>
      <div className="flex items-center gap-2">
        <span className="label-sm">論文上限</span>
        <input
          type="number"
          min={1}
          max={50}
          className="w-16 border-b border-border bg-transparent pb-1 text-center text-sm text-foreground outline-none focus:border-accent"
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value) || 1)}
          disabled={disabled}
        />
      </div>
    </form>
  );
}
