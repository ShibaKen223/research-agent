export type MarkdownItem = { heading: string; body: string };
export type SplitSection = { preamble: string; items: MarkdownItem[] };

function splitByH3Headers(body: string): MarkdownItem[] {
  const parts = body.split(/^### /m).filter((p) => p.trim());
  return parts.map((part) => {
    const [heading, ...rest] = part.split("\n");
    return { heading: heading.trim(), body: rest.join("\n").trim() };
  });
}

/** Fallback for older reports that used a plain numbered list instead of `### ` headers. */
function splitByNumberedList(body: string): MarkdownItem[] {
  const parts = body.split(/^\d+\.\s+/m).filter((p) => p.trim());
  return parts.map((part) => {
    const [first, ...rest] = part.split("\n");
    const heading = first.trim().replace(/\*\*/g, "");
    return { heading, body: rest.join("\n").trim() };
  });
}

/**
 * Split a section body into items (used by 研究趨勢/研究缺口/碩論題目建議).
 *
 * Any text *before* the first item — e.g. the unverified-section caveat that
 * report.py injects right under the heading — is returned as `preamble` so the
 * caller can render it as a banner instead of mis-parsing it into a bogus card.
 */
export function splitByH3(body: string): SplitSection {
  const h3 = /^### /m;
  if (h3.test(body)) {
    const idx = body.search(h3);
    const items = splitByH3Headers(body.slice(idx));
    if (items.length >= 1) return { preamble: body.slice(0, idx).trim(), items };
  }

  const num = /^\d+\.\s+/m;
  if (num.test(body)) {
    const idx = body.search(num);
    const items = splitByNumberedList(body.slice(idx));
    if (items.length > 1) return { preamble: body.slice(0, idx).trim(), items };
  }

  return { preamble: "", items: body.trim() ? [{ heading: "", body: body.trim() }] : [] };
}
