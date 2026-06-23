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
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-8 py-20">
      <header className="mb-20 flex flex-col gap-6">
        <p className="label-sm">Research Tool</p>
        <h1 className="font-display text-6xl leading-[1.1] tracking-tight sm:text-7xl">
          Research<br />Agent
        </h1>
        <p className="max-w-md text-lg text-muted">
          輸入關鍵字，搜尋文獻並產出 AI 研究分析報告
        </p>
      </header>

      <SearchBar onSearch={handleSearch} disabled={job !== null && job.status !== "error"} />

      {isEmpty ? (
        <div className="mt-20 flex flex-col items-start gap-3">
          <p className="label-sm">No reports yet</p>
          <p className="text-2xl text-muted">輸入關鍵字，開始你的第一份研究分析</p>
        </div>
      ) : (
        <section className="mt-16 flex flex-col gap-8">
          <div className="flex items-baseline justify-between">
            <p className="label-sm">已產出的報告</p>
            <p className="label-sm">{reports?.length} reports</p>
          </div>
          <div className="border-t border-border" />
          <div className="flex flex-col gap-0">
            {reports?.map((r, i) => (
              <ReportCard key={r.filename} report={r} index={i} />
            ))}
          </div>
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
