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

export function exportUrl(filename: string, fmt: "bib" | "ris"): string {
  const tokenParam = API_TOKEN ? `?token=${encodeURIComponent(API_TOKEN)}` : "";
  return `${BASE_URL}/api/reports/${encodeURIComponent(filename)}/export/${fmt}${tokenParam}`;
}

// Fetch the citation export and trigger a browser download. Unlike the Markdown
// download (a plain <a>, since the report always exists), the .bib/.ris exports
// are only present for reports produced after that feature shipped — so we fetch
// first and let the caller surface a clean message on 404 instead of navigating
// the user to a raw JSON error page.
export async function downloadExport(filename: string, fmt: "bib" | "ris"): Promise<void> {
  const headers = new Headers();
  if (API_TOKEN) headers.set("X-API-Token", API_TOKEN);
  const res = await fetch(exportUrl(filename, fmt), { headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.replace(/\.md$/, `.${fmt}`);
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
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
      // Fallback defaults mirror the backend's (translate + relevance on, paid
      // claim check off), so an omitted option never silently flips a default.
      translate: options?.translate ?? true,
      relevance_filter: options?.relevanceFilter ?? true,
      verify_claims: options?.verifyClaims ?? false,
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
