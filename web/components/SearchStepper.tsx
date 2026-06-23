import type { JobStatus } from "@/lib/types";

const STEPS: { key: JobStatus; label: string; icon: string }[] = [
  { key: "searching", label: "正在搜尋 Semantic Scholar", icon: "🔍" },
  { key: "analyzing", label: "AI 正在分析論文", icon: "🤖" },
  { key: "writing", label: "正在產生報告", icon: "📝" },
];

function stepIndex(status: JobStatus): number {
  if (status === "done") return STEPS.length;
  return STEPS.findIndex((s) => s.key === status);
}

export function SearchStepper({
  status,
  message,
  onDismiss,
}: {
  status: JobStatus;
  message: string;
  onDismiss?: () => void;
}) {
  const current = stepIndex(status);
  const failed = status === "error";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-white/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-8 shadow-lg">
        <h2 className="mb-6 text-lg font-semibold">
          {failed ? "搜尋失敗" : "正在產生研究報告"}
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
        {failed && (
          <>
            <p className="mt-6 text-sm text-red-400">{message}</p>
            <button
              onClick={onDismiss}
              className="mt-4 w-full rounded-lg border border-border px-4 py-2 text-sm text-foreground hover:bg-surface-hover"
            >
              關閉
            </button>
          </>
        )}
      </div>
    </div>
  );
}
