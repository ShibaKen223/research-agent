import Link from "next/link";
import type { ReportSummary } from "@/lib/types";

const SECTION_ICONS = ["📑", "📈", "🕳️", "🎓"];

export function ReportCard({ report }: { report: ReportSummary }) {
  return (
    <Link
      href={`/reports/${encodeURIComponent(report.filename)}`}
      className="group flex flex-col gap-3 rounded-2xl border border-border bg-surface p-5 transition hover:border-accent hover:bg-surface-hover"
    >
      <h3 className="truncate text-lg font-semibold text-foreground group-hover:text-accent">
        {report.keyword}
      </h3>
      <div className="flex items-center gap-4 text-sm text-muted">
        <span>{report.date ?? "—"}</span>
        <span>{report.paper_count ?? "—"} 篇論文</span>
      </div>
      <div className="mt-auto flex gap-2 text-xl">
        {SECTION_ICONS.map((icon) => (
          <span key={icon} className="opacity-70">
            {icon}
          </span>
        ))}
      </div>
    </Link>
  );
}
