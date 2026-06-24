export type ReportSummary = {
  filename: string;
  keyword: string;
  date: string | null;
  paper_count: string | null;
};

export type ReportDetail = {
  filename: string;
  meta: Record<string, string>;
  sections: Record<string, string>;
  section_order: string[];
  matrix: Record<string, string>[] | null;
  year_counts: Record<string, number>;
  raw: string;
};

export type SortMode = "relevance" | "citations";

export type SearchOptions = {
  sort: SortMode;
  minCitations: number;
  yearFrom: number | null;
  translate: boolean;
};

export type JobStatus = "searching" | "analyzing" | "writing" | "done" | "error";

export type Job = {
  status: JobStatus;
  message: string;
  report_filename: string | null;
  suggestions: string[] | null;
};
