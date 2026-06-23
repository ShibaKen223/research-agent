export type MarkdownItem = { heading: string; body: string };

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

/** Split a section body into items (used by 研究趨勢/研究缺口/碩論題目建議). */
export function splitByH3(body: string): MarkdownItem[] {
  const h3Items = splitByH3Headers(body);
  if (h3Items.length > 1) return h3Items;

  const numberedItems = splitByNumberedList(body);
  if (numberedItems.length > 1) return numberedItems;

  return body.trim() ? [{ heading: "", body: body.trim() }] : [];
}
