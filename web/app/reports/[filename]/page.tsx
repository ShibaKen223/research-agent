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

const SECTION_ICONS: Record<string, string> = {
  文獻矩陣: "📑",
  研究趨勢: "📈",
  研究缺口: "🕳️",
  碩論題目建議: "🎓",
};

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
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-6 py-12">
      <div>
        <nav className="text-sm text-muted">
          <Link href="/" className="hover:text-accent">
            首頁
          </Link>{" "}
          / <span className="text-foreground">{report.meta.關鍵字 ?? report.filename}</span>
        </nav>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">{report.meta.關鍵字}</h1>
            <div className="mt-2 flex gap-4 text-sm text-muted">
              <span>📅 {report.meta.產生日期}</span>
              <span>📄 {report.meta.分析論文數量} 篇論文</span>
              <span>來源：Semantic Scholar</span>
            </div>
          </div>
          <div className="flex gap-2">
            <a
              href={downloadUrl(report.filename)}
              className="rounded-xl border border-border px-4 py-2 text-sm hover:bg-surface-hover"
            >
              ⬇️ 下載 Markdown
            </a>
            <button
              onClick={handleDelete}
              className="rounded-xl border border-border px-4 py-2 text-sm text-red-400 hover:bg-surface-hover"
            >
              🗑️ 刪除
            </button>
          </div>
        </div>
      </div>

      <div className="sticky top-0 z-10 -mx-6 flex gap-2 bg-background px-6 py-3">
        {report.section_order.map((title) => (
          <button
            key={title}
            onClick={() => setActiveTab(title)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
              activeTab === title
                ? "bg-accent text-accent-foreground"
                : "text-muted hover:bg-surface-hover hover:text-foreground"
            }`}
          >
            {SECTION_ICONS[title] ?? "📄"} {title}
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
