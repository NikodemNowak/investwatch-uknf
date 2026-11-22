/** Post text with the quoted evidence marked. */
export function QuotedText({ text, quotes }: { text: string; quotes: string[] }) {
  const needles = [
    ...new Set(quotes.map((q) => q.replace(/…$/, "").trim()).filter((q) => q.length > 3)),
  ];
  const ranges: [number, number][] = [];
  for (const needle of needles) {
    let from = 0;
    for (;;) {
      const at = text.indexOf(needle, from);
      if (at < 0) break;
      ranges.push([at, at + needle.length]);
      from = at + needle.length;
    }
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const parts: { text: string; mark: boolean }[] = [];
  let cursor = 0;
  for (const [start, end] of ranges) {
    if (end <= cursor) continue;
    const s = Math.max(start, cursor);
    if (s > cursor) parts.push({ text: text.slice(cursor, s), mark: false });
    parts.push({ text: text.slice(s, end), mark: true });
    cursor = end;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), mark: false });
  return (
    <div className="shot__text">
      {parts.map((part, index) =>
        part.mark ? <mark key={index}>{part.text}</mark> : <span key={index}>{part.text}</span>,
      )}
    </div>
  );
}
