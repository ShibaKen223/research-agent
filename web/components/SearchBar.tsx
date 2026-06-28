"use client";

import { useState } from "react";
import { suggestAcademicTerms } from "@/lib/api";
import type { AcademicTerm, SearchOptions, SortMode } from "@/lib/types";

type Props = {
  onSearch: (keyword: string, limit: number, options: SearchOptions) => void;
  disabled?: boolean;
};

export function SearchBar({ onSearch, disabled }: Props) {
  const [keyword, setKeyword] = useState("");
  const [limit, setLimit] = useState(20);
  const [sort, setSort] = useState<SortMode>("relevance");
  const [minCitations, setMinCitations] = useState(0);
  const [yearFrom, setYearFrom] = useState<number | "">("");
  // Default-on, matching the CLI/API: non-ASCII keywords are dual-queried
  // (original + English translation) for far better coverage.
  const [translate, setTranslate] = useState(true);
  const [terms, setTerms] = useState<AcademicTerm[] | null>(null);
  const [loadingTerms, setLoadingTerms] = useState(false);
  const [termsError, setTermsError] = useState<string | null>(null);

  const handleSuggestTerms = async () => {
    if (!keyword.trim()) return;
    setLoadingTerms(true);
    setTermsError(null);
    try {
      const { terms } = await suggestAcademicTerms(keyword.trim());
      setTerms(terms);
    } catch (e) {
      setTerms(null);
      setTermsError(e instanceof Error ? e.message : "建議失敗，請稍後再試。");
    } finally {
      setLoadingTerms(false);
    }
  };

  return (
    <form
      className="flex flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (keyword.trim()) {
          onSearch(keyword.trim(), limit, {
            sort,
            minCitations,
            yearFrom: yearFrom === "" ? null : yearFrom,
            translate,
          });
        }
      }}
    >
      <div className="flex items-end gap-7">
        <input
          className="font-display flex-1 border-b border-foreground bg-transparent pb-3.5 text-2xl text-foreground outline-none not-italic placeholder:text-muted/50 placeholder:not-italic focus:border-accent sm:text-3xl"
          placeholder="輸入研究關鍵字"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          disabled={disabled}
        />
        <button
          type="submit"
          disabled={disabled || !keyword.trim()}
          className="font-display shrink-0 whitespace-nowrap rounded-lg bg-foreground px-11 py-3.5 text-[22px] font-semibold tracking-wide text-accent-foreground not-italic transition hover:bg-accent disabled:opacity-30"
        >
          搜尋&nbsp;→
        </button>
      </div>
      <div className="flex items-center gap-4">
        <span className="label-sm">論文上限</span>
        <div className="flex items-center gap-3.5">
          <button
            type="button"
            disabled={disabled}
            onClick={() => setLimit((l) => Math.max(1, l - 1))}
            className="flex h-6.5 w-6.5 items-center justify-center rounded-full border border-border-hover text-sm leading-none text-foreground transition hover:border-accent hover:text-accent disabled:opacity-30"
          >
            –
          </button>
          <span className="font-display min-w-[28px] text-center text-2xl not-italic">{limit}</span>
          <button
            type="button"
            disabled={disabled}
            onClick={() => setLimit((l) => Math.min(50, l + 1))}
            className="flex h-6.5 w-6.5 items-center justify-center rounded-full border border-border-hover text-sm leading-none text-foreground transition hover:border-accent hover:text-accent disabled:opacity-30"
          >
            +
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
        <div className="flex items-center gap-3">
          <span className="label-sm">排序方式</span>
          <div className="flex gap-2">
            {([
              { key: "relevance", label: "相關度" },
              { key: "citations", label: "引用數" },
            ] as const).map((opt) => (
              <button
                key={opt.key}
                type="button"
                disabled={disabled}
                onClick={() => setSort(opt.key)}
                className={`label-sm rounded-full border px-4 py-1.5 transition disabled:opacity-30 ${
                  sort === opt.key
                    ? "border-accent bg-accent text-accent-foreground"
                    : "border-border-hover text-muted hover:border-accent hover:text-accent"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="label-sm">最低引用數</span>
          <input
            type="number"
            min={0}
            disabled={disabled}
            value={minCitations || ""}
            onChange={(e) => setMinCitations(Math.max(0, Number(e.target.value) || 0))}
            placeholder="0"
            className="w-16 border-b border-border-hover bg-transparent pb-1 text-sm text-foreground outline-none focus:border-accent"
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="label-sm">起始年份</span>
          <input
            type="number"
            min={1900}
            max={2100}
            disabled={disabled}
            value={yearFrom}
            onChange={(e) => setYearFrom(e.target.value === "" ? "" : Number(e.target.value))}
            placeholder="不限"
            className="w-20 border-b border-border-hover bg-transparent pb-1 text-sm text-foreground outline-none focus:border-accent"
          />
        </div>

        <div className="flex items-center gap-3">
          <span
            className="label-sm"
            title="中文關鍵字會同時用原文與 Haiku 英譯詞「雙查」再合併，大幅提升英文語料庫命中率；純英文關鍵字會自動略過、不額外花費。"
          >
            關鍵字翻譯
          </span>
          <button
            type="button"
            disabled={disabled}
            onClick={() => setTranslate((v) => !v)}
            aria-pressed={translate}
            className={`label-sm rounded-full border px-4 py-1.5 transition disabled:opacity-30 ${
              translate
                ? "border-accent bg-accent text-accent-foreground"
                : "border-border-hover text-muted hover:border-accent hover:text-accent"
            }`}
          >
            {translate ? "中→英 已開" : "中→英 關"}
          </button>
        </div>

        <button
          type="button"
          disabled={disabled || !keyword.trim() || loadingTerms}
          onClick={handleSuggestTerms}
          title="不熟悉領域術語時，用 Haiku 建議學術界常用的英文檢索詞"
          className="label-sm rounded-full border border-border-hover px-4 py-1.5 text-muted transition hover:border-accent hover:text-accent disabled:opacity-30"
        >
          {loadingTerms ? "建議中…" : "學術用語建議"}
        </button>
      </div>

      {termsError && <p className="text-sm text-red-400">{termsError}</p>}

      {!!terms?.length && (
        <div className="flex flex-col gap-3">
          <p className="label-sm text-muted-strong">建議學術檢索詞（點選帶入搜尋框）</p>
          <div className="flex flex-wrap gap-2">
            {terms.map((t) => (
              <button
                key={t.term}
                type="button"
                disabled={disabled}
                title={t.gloss}
                onClick={() => {
                  setKeyword(t.term);
                  setTerms(null);
                }}
                className="label-sm rounded-full border border-border-hover px-4 py-1.5 text-foreground transition hover:border-accent hover:text-accent disabled:opacity-30"
              >
                {t.term}
                {t.gloss && <span className="ml-1.5 text-muted">· {t.gloss}</span>}
              </button>
            ))}
          </div>
        </div>
      )}
    </form>
  );
}
