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

export type AcademicTerm = {
  term: string;
  gloss: string;
};

export type SortMode = "relevance" | "citations";

export type SearchOptions = {
  sort: SortMode;
  minCitations: number;
  yearFrom: number | null;
  translate: boolean;
  // Default-on: drop off-topic (keyword-coincidence) papers with a cheap Haiku
  // pass before the paid analysis.
  relevanceFilter: boolean;
  // On by default: the cheap, cached Haiku check that each 主要發現 is
  // abstract-supported (guards over-claiming).
  verifyClaims: boolean;
  // Off by default: paid + network. Pull OA full text (arXiv / Unpaywall) and
  // extract authors' stated methods/limitations (OA subset only).
  fulltext: boolean;
  // Off by default: cross-check the topic against existing Taiwan theses via the
  // official NCL open data (title-level; downloads CSVs + a Haiku scoring call).
  ndltd: boolean;
};

export type JobStatus = "searching" | "analyzing" | "writing" | "done" | "error";

export type Job = {
  status: JobStatus;
  message: string;
  report_filename: string | null;
  suggestions: string[] | null;
};
