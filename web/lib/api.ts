import type { AcademicTerm, Job, ReportDetail, ReportSummary, SearchOptions } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (API_TOKEN) headers.set("X-API-Token", API_TOKEN);
  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export function listReports(): Promise<ReportSummary[]> {
  return request("/api/reports");
}

export function getReport(filename: string): Promise<ReportDetail> {
  return request(`/api/reports/${encodeURIComponent(filename)}`);
}

export function deleteReport(filename: string): Promise<{ ok: boolean }> {
  return request(`/api/reports/${encodeURIComponent(filename)}`, { method: "DELETE" });
}

export function downloadUrl(filename: string): string {
  const tokenParam = API_TOKEN ? `?token=${encodeURIComponent(API_TOKEN)}` : "";
  return `${BASE_URL}/api/reports/${encodeURIComponent(filename)}/download${tokenParam}`;
}

export function startSearch(
  keyword: string,
  limit: number,
  options?: SearchOptions
): Promise<{ job_id: string }> {
  return request("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      keyword,
      limit,
      sort: options?.sort ?? "relevance",
      min_citations: options?.minCitations ?? 0,
      year_from: options?.yearFrom ?? null,
      translate: options?.translate ?? false,
    }),
  });
}

export function getJob(jobId: string): Promise<Job> {
  return request(`/api/jobs/${jobId}`);
}

export function suggestAcademicTerms(keyword: string): Promise<{ terms: AcademicTerm[] }> {
  return request("/api/suggest-terms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keyword }),
  });
}
