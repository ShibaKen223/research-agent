import type { JobStatus } from "@/lib/types";

const STEPS: { key: JobStatus; label: string; icon: string }[] = [
  { key: "searching", label: "正在搜尋 Semantic Scholar、OpenAlex、arXiv", icon: "1" },
  { key: "analyzing", label: "AI 正在分析論文", icon: "2" },
  { key: "writing", label: "正在產生報告", icon: "3" },
];

function stepIndex(status: JobStatus): number {
  if (status === "done") return STEPS.length;
  return STEPS.findIndex((s) => s.key === status);
}

export function SearchStepper({
  status,
  message,
  suggestions,
  onDismiss,
  onSelectSuggestion,
  onViewReport,
}: {
  status: JobStatus;
  message: string;
  suggestions?: string[] | null;
  onDismiss?: () => void;
  onSelectSuggestion?: (keyword: string) => void;
  onViewReport?: () => void;
}) {
  const current = stepIndex(status);
  const failed = status === "error";
  const sparseDone = status === "done" && !!suggestions?.length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-lg border border-border bg-surface p-8 shadow-lg">
        <h2 className="font-display mb-6 text-2xl not-italic">
          {failed ? "搜尋失敗" : sparseDone ? "報告已完成，但論文較少" : "正在產生研究報告"}
        </h2>
        <ol className="flex flex-col gap-4">
          {STEPS.map((step, i) => {
            const done = !failed && i < current;
            const active = !failed && i === current;
            return (
              <li key={step.key} className="flex items-center gap-3">
                <span className="relative flex h-6 w-6 shrink-0 items-center justify-center">
                  {active && (
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent/40" />
                  )}
                  <span
                    className={`relative flex h-6 w-6 items-center justify-center rounded-full border text-xs ${
                      done
                        ? "border-teal bg-teal/10 text-teal"
                        : active
                          ? "border-accent bg-accent/10 text-accent"
                          : "border-border text-muted"
                    }`}
                  >
                    {done ? "✓" : step.icon}
                  </span>
                </span>
                <span className={active ? "text-foreground" : "text-muted"}>{step.label}</span>
              </li>
            );
          })}
        </ol>
        {failed && <p className="mt-6 text-sm text-red-400">{message}</p>}
        {!!suggestions?.length && (failed || sparseDone) && (
          <div className="mt-6">
            <p className="text-sm text-muted">可以試試這些關鍵字：</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => onSelectSuggestion?.(s)}
                  className="label-sm rounded-full border border-border-hover px-4 py-1.5 text-foreground transition hover:border-accent hover:text-accent"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {(failed || sparseDone) && (
          <div className="mt-6 flex gap-3">
            {sparseDone && (
              <button
                onClick={onViewReport}
                className="flex-1 rounded-lg bg-foreground px-4 py-2 text-sm font-semibold text-accent-foreground hover:bg-accent"
              >
                查看報告 →
              </button>
            )}
            <button
              onClick={onDismiss}
              className="flex-1 rounded-lg border border-border px-4 py-2 text-sm text-foreground hover:bg-surface-hover"
            >
              關閉
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
