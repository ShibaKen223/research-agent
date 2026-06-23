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
      className="flex w-full flex-col gap-3 sm:flex-row sm:items-center"
      onSubmit={(e) => {
        e.preventDefault();
        if (keyword.trim()) onSearch(keyword.trim(), limit);
      }}
    >
      <input
        className="flex-1 rounded-xl border border-border bg-surface px-5 py-4 text-lg text-foreground placeholder:text-muted outline-none focus:border-accent"
        placeholder="輸入研究關鍵字，例如：AI supply chain"
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
        disabled={disabled}
      />
      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-muted">
          論文數量上限
          <input
            type="number"
            min={1}
            max={50}
            className="w-20 rounded-lg border border-border bg-surface px-2 py-2 text-foreground outline-none focus:border-accent"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value) || 1)}
            disabled={disabled}
          />
        </label>
        <button
          type="submit"
          disabled={disabled || !keyword.trim()}
          className="rounded-xl bg-accent px-6 py-4 font-semibold text-accent-foreground transition hover:opacity-90 disabled:opacity-40"
        >
          搜尋
        </button>
      </div>
    </form>
  );
}
