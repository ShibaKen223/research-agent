import Link from "next/link";
import type { ReportSummary } from "@/lib/types";

export function ReportCard({ report, index = 0 }: { report: ReportSummary; index?: number }) {
  const num = String(index + 1).padStart(2, "0");
  return (
    <Link
      href={`/reports/${encodeURIComponent(report.filename)}`}
      style={{ animationDelay: `${index * 60}ms` }}
      className="animate-fade-in-up group flex items-baseline gap-8 border-b border-border py-6 transition-colors hover:bg-surface-hover"
    >
      <span className="label-sm w-8 shrink-0">{num}</span>
      <div className="flex flex-1 items-baseline justify-between gap-4">
        <h3 className="font-display text-3xl tracking-tight group-hover:text-accent sm:text-4xl">
          {report.keyword}
        </h3>
        <div className="flex items-center gap-6">
          <span className="label-sm hidden sm:inline">{report.paper_count ?? "—"} papers</span>
          <span className="label-sm">{report.date ?? "—"}</span>
          <span className="text-accent transition-transform group-hover:translate-x-1">→</span>
        </div>
      </div>
    </Link>
  );
}
