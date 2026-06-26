"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getJob, listReports, startSearch } from "@/lib/api";
import { ReportCard } from "@/components/ReportCard";
import { RippleCanvas } from "@/components/RippleCanvas";
import { SearchBar } from "@/components/SearchBar";
import { SearchStepper } from "@/components/SearchStepper";
import { WorkflowModal } from "@/components/WorkflowModal";
import type { Job, ReportSummary, SearchOptions } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [showWorkflow, setShowWorkflow] = useState(false);
  const reportsRef = useRef<HTMLDivElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollFailuresRef = useRef(0);
  const lastSearchRef = useRef<{ limit: number; options: SearchOptions } | null>(null);

  useEffect(() => {
    listReports()
      .then((r) => {
        setReports(r);
        setLoadError(false);
      })
      // Distinguish a real fetch failure (backend down / auth blocked) from a
      // genuinely empty library — otherwise both look like "no reports yet".
      .catch(() => {
        setReports([]);
        setLoadError(true);
      });
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleSearch = async (keyword: string, limit: number, options: SearchOptions) => {
    lastSearchRef.current = { limit, options };
    const { job_id } = await startSearch(keyword, limit, options);
    setJob({ status: "searching", message: "排隊中...", report_filename: null, suggestions: null });
    pollFailuresRef.current = 0;

    pollRef.current = setInterval(async () => {
      try {
        const latest = await getJob(job_id);
        pollFailuresRef.current = 0;
        setJob(latest);
        if (latest.status === "done" && latest.report_filename) {
          if (pollRef.current) clearInterval(pollRef.current);
          // Sparse results: let the user see the suggestions instead of whisking them away.
          if (!latest.suggestions?.length) {
            router.push(`/reports/${encodeURIComponent(latest.report_filename)}`);
          }
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
            suggestions: null,
          });
        }
      }
    }, 1200);
  };

  const isEmpty = reports !== null && reports.length === 0;
  const year = new Date().getFullYear();
  const ticks = Array.from({ length: 9 }, (_, i) => String(i + 1).padStart(2, "0"));

  return (
    <div ref={rootRef} className="relative flex-1 overflow-hidden">
      <RippleCanvas containerRef={rootRef} />

      <div className="ra-corner left-[26px] top-[26px] border-l border-t" />
      <div className="ra-corner right-[26px] top-[26px] border-r border-t" />
      <div className="ra-corner bottom-[26px] left-[26px] border-b border-l" />
      <div className="ra-corner bottom-[26px] right-[26px] border-b border-r" />

      <div className="pointer-events-none absolute top-[120px] right-[-120px] z-[1] hidden h-[920px] w-[920px] opacity-50 lg:block">
        <svg
          width="920"
          height="920"
          viewBox="0 0 430 430"
          className="absolute inset-0"
          style={{ animation: "ra-spin 80s linear infinite" }}
        >
          <circle cx="215" cy="215" r="206" fill="none" stroke="#CFC6B8" strokeWidth="0.6" strokeDasharray="2 9" />
        </svg>
        <svg
          width="920"
          height="920"
          viewBox="0 0 430 430"
          className="absolute inset-0"
          style={{ animation: "ra-spin 56s linear infinite reverse" }}
        >
          <circle cx="215" cy="215" r="168" fill="none" stroke="#D2C9BB" strokeWidth="0.6" />
          <circle cx="215" cy="47" r="4" fill="var(--accent)" opacity="0.55" />
        </svg>
        <svg width="920" height="920" viewBox="0 0 430 430" className="absolute inset-0">
          <circle cx="215" cy="215" r="132" fill="none" stroke="#C7BEAF" strokeWidth="0.6" />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-serif text-[480px] leading-none font-medium not-italic" style={{ color: "#D8CFC0" }}>
            R
            <span className="relative -top-[250px] -left-[28px] text-[130px]" style={{ color: "#E2A48C" }}>
              *
            </span>
          </span>
        </div>
      </div>

      <header className="relative z-[3] flex items-start justify-between px-8 pt-12 sm:px-[60px]">
        <div className="flex items-start gap-8 sm:gap-[54px]">
          <div className="font-display text-3xl leading-none tracking-wide not-italic">
            R<span className="text-accent">.</span>
          </div>
          <div>
            <div className="font-display text-xl leading-none not-italic">Agent</div>
            <div className="label-sm mt-2">RESEARCH ENGINE</div>
          </div>
        </div>
        <nav className="hidden items-start gap-12 sm:flex">
          <button
            type="button"
            className="ra-nav text-left transition-colors"
            onClick={() => reportsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
          >
            <div className="font-display text-xl leading-none not-italic">Library</div>
            <div className="label-sm mt-2">SAVED REPORTS</div>
          </button>
          <button
            type="button"
            className="ra-nav text-left transition-colors"
            onClick={() => setShowWorkflow(true)}
          >
            <div className="font-display text-xl leading-none not-italic">Workflow</div>
            <div className="label-sm mt-2">HOW IT WORKS</div>
          </button>
        </nav>
      </header>

      <div className="relative z-[2] mx-8 mt-16 flex justify-between border-t border-border sm:mx-[60px]">
        {ticks.map((t) => (
          <span key={t} className="label-sm pt-2">
            {t}
          </span>
        ))}
      </div>

      <main className="relative z-[2] px-8 sm:px-[60px]">
        <div className="mt-8 flex items-center justify-between">
          <div>
            <p className="label-sm mb-4 text-accent">
              RESEARCH TOOL <span className="text-muted">/ {year}</span>
            </p>
            <h1 className="font-serif text-[64px] leading-[0.92] font-medium tracking-tight not-italic sm:text-[96px] lg:text-[116px]">
              Research<br />Agent
            </h1>
            <p className="mt-6 max-w-md text-base leading-relaxed text-muted-strong">
              輸入關鍵字，搜尋文獻並產出 AI 研究分析報告。
            </p>
          </div>
        </div>

        <div className="mt-14">
          <SearchBar onSearch={handleSearch} disabled={job !== null && job.status !== "error"} />
        </div>

        <div ref={reportsRef}>
          {loadError ? (
            <div className="mt-20 flex flex-col items-start gap-3 pb-24">
              <p className="label-sm text-accent">Connection error</p>
              <p className="text-2xl text-muted">
                無法連線到後端，請確認伺服器仍在執行後重新整理頁面。
              </p>
            </div>
          ) : isEmpty ? (
            <div className="mt-20 flex flex-col items-start gap-3 pb-24">
              <p className="label-sm">No reports yet</p>
              <p className="text-2xl text-muted">輸入關鍵字，開始你的第一份研究分析</p>
            </div>
          ) : (
            <section className="mt-20">
              <div className="flex items-baseline justify-between">
                <p className="label-sm text-muted-strong">已產出的報告</p>
                <p className="label-sm">{reports?.length} REPORTS</p>
              </div>
              <div className="mt-4 h-px bg-border" />
              <div className="flex flex-col gap-0 pb-24">
                {reports?.map((r, i) => (
                  <ReportCard key={r.filename} report={r} index={i} />
                ))}
              </div>
            </section>
          )}
        </div>
      </main>

      <div className="label-sm absolute bottom-11 left-8 z-[3] sm:left-[60px]">
        SEMANTIC SCHOLAR · OPENALEX
      </div>
      <div className="label-sm absolute bottom-11 right-8 z-[3] text-accent sm:right-[60px]">
        POWERED BY CLAUDE
      </div>

      {job && (
        <SearchStepper
          status={job.status}
          message={job.message}
          suggestions={job.suggestions}
          onDismiss={() => setJob(null)}
          onViewReport={() => {
            if (job.report_filename) router.push(`/reports/${encodeURIComponent(job.report_filename)}`);
          }}
          onSelectSuggestion={(keyword) => {
            const { limit, options } = lastSearchRef.current ?? {
              limit: 20,
              options: { sort: "relevance", minCitations: 0, yearFrom: null, translate: false },
            };
            handleSearch(keyword, limit, options);
          }}
        />
      )}

      {showWorkflow && <WorkflowModal onDismiss={() => setShowWorkflow(false)} />}
    </div>
  );
}
