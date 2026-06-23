import type { Job, ReportDetail, ReportSummary } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init);
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
  return `${BASE_URL}/api/reports/${encodeURIComponent(filename)}/download`;
}

export function startSearch(keyword: string, limit: number): Promise<{ job_id: string }> {
  return request("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keyword, limit }),
  });
}

export function getJob(jobId: string): Promise<Job> {
  return request(`/api/jobs/${jobId}`);
}
