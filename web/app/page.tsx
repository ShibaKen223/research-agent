"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getJob, listReports, startSearch } from "@/lib/api";
import { ReportCard } from "@/components/ReportCard";
import { SearchBar } from "@/components/SearchBar";
import { SearchStepper } from "@/components/SearchStepper";
import type { Job, ReportSummary } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollFailuresRef = useRef(0);

  useEffect(() => {
    listReports().then(setReports).catch(() => setReports([]));
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleSearch = async (keyword: string, limit: number) => {
    const { job_id } = await startSearch(keyword, limit);
    setJob({ status: "searching", message: "排隊中...", report_filename: null });
    pollFailuresRef.current = 0;

    pollRef.current = setInterval(async () => {
      try {
        const latest = await getJob(job_id);
        pollFailuresRef.current = 0;
        setJob(latest);
        if (latest.status === "done" && latest.report_filename) {
          if (pollRef.current) clearInterval(pollRef.current);
          router.push(`/reports/${encodeURIComponent(latest.report_filename)}`);
        } else if (latest.status === "error") {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch (e) {
        pollFailuresRef.current += 1;
        if (pollFailuresRef.current >= 3) {
          if (pollRef.current) clearInterval(pollRef.current);
          setJob({
            status: "error",
            message: "與伺服器失去連線，請確認後端是否仍在執行。",
            report_filename: null,
          });
        }
      }
    }, 1200);
  };

  const isEmpty = reports !== null && reports.length === 0;

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-10 px-6 py-16">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">📚 Research Agent</h1>
        <p className="mt-1 text-muted">輸入關鍵字，搜尋文獻並產出 AI 研究分析報告</p>
      </header>

      <SearchBar onSearch={handleSearch} disabled={job !== null && job.status !== "error"} />

      {isEmpty ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border py-24 text-center">
          <span className="text-5xl">🔭</span>
          <p className="text-lg text-foreground">還沒有任何報告</p>
          <p className="text-muted">輸入關鍵字，開始你的第一份研究分析</p>
        </div>
      ) : (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {reports?.map((r) => (
            <ReportCard key={r.filename} report={r} />
          ))}
        </section>
      )}

      {job && (
        <SearchStepper
          status={job.status}
          message={job.message}
          onDismiss={() => setJob(null)}
        />
      )}
    </main>
  );
}
