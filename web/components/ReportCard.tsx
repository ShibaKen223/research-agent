import Link from "next/link";
import type { ReportSummary } from "@/lib/types";

export function ReportCard({ report, index = 0 }: { report: ReportSummary; index?: number }) {
  const num = String(index + 1).padStart(2, "0");
  return (
    <Link
      href={`/reports/${encodeURIComponent(report.filename)}`}
      style={{ animationDelay: `${index * 60}ms` }}
      className="ra-row animate-fade-in-up relative flex items-baseline gap-8 py-7"
    >
      <span className="ra-rule absolute bottom-0 left-0 h-px w-full bg-border transition-colors" />
      <span className="label-sm w-8 shrink-0">{num}</span>
      <div className="flex flex-1 items-baseline justify-between gap-4">
        <h3 className="ra-title font-display text-3xl tracking-tight transition-colors sm:text-4xl">
          {report.keyword}
        </h3>
        <div className="flex items-center gap-6">
          <span className="label-sm hidden sm:inline">{report.paper_count ?? "—"} PAPERS</span>
          <span className="label-sm">{report.date ?? "—"}</span>
          <span className="ra-arrow inline-block text-base text-foreground transition-all">→</span>
        </div>
      </div>
    </Link>
  );
}
