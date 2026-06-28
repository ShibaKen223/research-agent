"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import { deleteReport, downloadUrl, getReport } from "@/lib/api";
import { splitByH3 } from "@/lib/markdown";
import { MatrixTable } from "@/components/MatrixTable";
import { TrendCard } from "@/components/TrendCard";
import { GapCard } from "@/components/GapCard";
import { ThesisCard } from "@/components/ThesisCard";
import type { ReportDetail } from "@/lib/types";
import { useRouter } from "next/navigation";

export default function ReportPage({
  params,
}: {
  params: Promise<{ filename: string }>;
}) {
  const { filename: rawFilename } = use(params);
  const filename = decodeURIComponent(rawFilename);
  const router = useRouter();
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string | null>(null);

  useEffect(() => {
    getReport(filename)
      .then((r) => {
        setReport(r);
        setActiveTab(r.section_order[0] ?? null);
      })
      .catch((e) => setError(e.message));
  }, [filename]);

  if (error) {
    return (
      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-16">
        <p className="text-red-400">讀取報告失敗：{error}</p>
        <Link href="/" className="mt-4 inline-block text-accent hover:underline">
          ← 回首頁
        </Link>
      </main>
    );
  }

  if (!report) {
    return (
      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-16 text-muted">
        載入中...
      </main>
    );
  }

  const handleDelete = async () => {
    if (!confirm(`確定要刪除「${report.meta.關鍵字 ?? report.filename}」這份報告嗎？`)) return;
    await deleteReport(report.filename);
    router.push("/");
  };

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-8 py-12">
      <div>
        <nav className="label-sm">
          <Link href="/" className="hover:text-accent">
            首頁
          </Link>{" "}
          › <span className="text-foreground">{report.meta.關鍵字 ?? report.filename}</span>
        </nav>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-5xl tracking-tight sm:text-6xl">
              {report.meta.關鍵字}
            </h1>
            <div className="label-sm mt-3 flex gap-3">
              <span>{report.meta.產生日期}</span>
              <span>·</span>
              <span>{report.meta.分析論文數量} 篇論文</span>
              <span>·</span>
              <span>來源：{report.meta.資料來源 ?? "Semantic Scholar、OpenAlex"}</span>
            </div>
          </div>
          <div className="flex gap-1">
            <a
              href={downloadUrl(report.filename)}
              aria-label="下載 Markdown"
              title="下載 Markdown"
              className="rounded-lg p-2 text-muted transition hover:text-accent"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 3v12" />
                <path d="m7 10 5 5 5-5" />
                <path d="M5 21h14" />
              </svg>
            </a>
            <button
              onClick={handleDelete}
              aria-label="刪除"
              title="刪除"
              className="rounded-lg p-2 text-muted transition hover:text-accent"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M3 6h18" />
                <path d="M8 6V4h8v2" />
                <path d="M19 6l-1 14H6L5 6" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <div className="sticky top-0 z-10 -mx-8 flex gap-8 border-b border-border bg-background px-8 pt-2">
        {report.section_order.map((title) => (
          <button
            key={title}
            onClick={() => setActiveTab(title)}
            className={`-mb-px border-b-2 pb-4 text-sm transition ${
              activeTab === title
                ? "border-accent font-medium text-foreground"
                : "border-transparent text-muted hover:text-foreground"
            }`}
          >
            {title}
          </button>
        ))}
      </div>

      <div className="min-h-[300px]">
        {report.section_order.map((title) =>
          activeTab === title ? (
            <SectionContent key={title} title={title} report={report} />
          ) : null
        )}
      </div>
    </main>
  );
}

function SectionContent({ title, report }: { title: string; report: ReportDetail }) {
  const body = report.sections[title] ?? "";

  if (title === "文獻矩陣" && report.matrix) {
    return <MatrixTable rows={report.matrix} yearCounts={report.year_counts} />;
  }

  if (title === "研究趨勢") {
    const items = splitByH3(body);
    return (
      <div className="max-w-3xl">
        {items.map((item, i) => (
          <TrendCard key={item.heading} item={item} index={i} />
        ))}
      </div>
    );
  }

  if (title === "研究缺口") {
    const items = splitByH3(body);
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {items.map((item) => (
          <GapCard key={item.heading} item={item} />
        ))}
      </div>
    );
  }

  if (title === "碩論題目建議") {
    const items = splitByH3(body);
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {items.map((item) => (
          <ThesisCard key={item.heading} item={item} filename={report.filename} />
        ))}
      </div>
    );
  }

  return (
    <div className="prose-sm max-w-3xl [&_strong]:text-foreground">
      <ReactMarkdown>{body}</ReactMarkdown>
    </div>
  );
}
