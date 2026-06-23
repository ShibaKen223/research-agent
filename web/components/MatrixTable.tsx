"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function MatrixTable({
  rows,
  yearCounts,
}: {
  rows: Record<string, string>[];
  yearCounts: Record<string, number>;
}) {
  const columns = Object.keys(rows[0] ?? {});
  const [query, setQuery] = useState("");
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);

  const filtered = useMemo(() => {
    let data = rows;
    if (query.trim()) {
      const q = query.toLowerCase();
      data = data.filter((row) => columns.some((c) => row[c]?.toLowerCase().includes(q)));
    }
    if (sortCol) {
      data = [...data].sort((a, b) => {
        const cmp = (a[sortCol] ?? "").localeCompare(b[sortCol] ?? "", "zh-Hant");
        return sortAsc ? cmp : -cmp;
      });
    }
    return data;
  }, [rows, query, sortCol, sortAsc, columns]);

  const chartData = Object.entries(yearCounts).map(([year, count]) => ({ year, count }));

  return (
    <div className="flex flex-col gap-6">
      <input
        className="w-full max-w-sm rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-accent"
        placeholder="搜尋表格內容..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-hover text-muted">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  className="cursor-pointer select-none whitespace-nowrap px-4 py-3 hover:text-foreground"
                  onClick={() => {
                    if (sortCol === col) setSortAsc(!sortAsc);
                    else {
                      setSortCol(col);
                      setSortAsc(true);
                    }
                  }}
                >
                  {col} {sortCol === col ? (sortAsc ? "▲" : "▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((row, i) => (
              <tr key={i} className="border-t border-border align-top hover:bg-surface-hover">
                {columns.map((col) => (
                  <td key={col} className="max-w-xs px-4 py-3 text-foreground/90">
                    {row[col]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {chartData.length > 0 && (
        <div>
          <p className="mb-2 text-sm text-muted">各年份論文數量</p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="year" stroke="var(--muted)" />
              <YAxis allowDecimals={false} stroke="var(--muted)" />
              <Tooltip
                contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }}
              />
              <Bar dataKey="count" fill="var(--accent)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
