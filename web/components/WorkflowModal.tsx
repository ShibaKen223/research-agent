"use client";

const STEPS = [
  {
    num: "01",
    title: "搜尋",
    desc: "輸入研究關鍵字，從 Semantic Scholar、OpenAlex 與 arXiv 取得相關論文與摘要；中文關鍵字會自動以原文＋英譯雙查。",
  },
  {
    num: "02",
    title: "分析",
    desc: "Claude 閱讀論文摘要，整理出文獻矩陣、研究趨勢與研究缺口。",
  },
  {
    num: "03",
    title: "報告",
    desc: "產出包含碩論題目建議的完整研究報告，可隨時查閱與下載。",
  },
];

export function WorkflowModal({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm"
      onClick={onDismiss}
    >
      <div
        className="w-full max-w-lg rounded-lg border border-border bg-surface p-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-baseline justify-between">
          <h2 className="font-serif text-2xl font-medium not-italic">How it works</h2>
          <button
            type="button"
            onClick={onDismiss}
            aria-label="關閉"
            className="label-sm hover:text-accent"
          >
            關閉 ✕
          </button>
        </div>
        <div className="mt-6 h-px bg-border" />
        <ol className="mt-6 flex flex-col gap-6">
          {STEPS.map((step) => (
            <li key={step.num} className="flex items-start gap-5">
              <span className="label-sm w-6 shrink-0 pt-0.5 text-accent">{step.num}</span>
              <div>
                <h3 className="font-serif text-lg font-medium not-italic">{step.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-muted-strong">{step.desc}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
