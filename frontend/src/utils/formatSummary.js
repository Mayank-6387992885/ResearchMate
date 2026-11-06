const BULLET_LINE_PATTERN = /^\s*(?:[-*•]|\d+[.)])\s+/;
const SECTION_HEADING_PATTERN = /(?:Paper Overview|Problem Being Solved|Methodology|Key Findings|Limitations|Important Technical Terms|Final Takeaway|Recommendations|Conclusion)/;

export function formatSummaryText(summary) {
  if (typeof summary !== "string") return "";

  const normalizedSummary = summary
    .replace(/\r\n?/g, "\n")
    .replace(
      new RegExp(`([.!?])\\s+(?=\\*\\*${SECTION_HEADING_PATTERN.source}\\*\\*)`, "g"),
      "$1\n\n",
    )
    .replace(
      new RegExp(`(\\*\\*${SECTION_HEADING_PATTERN.source}\\*\\*)\\s+`, "g"),
      "$1\n\n",
    )
    .replace(/([.!?:])\s+([*•-])\s+(?=(?:\*\*)?[A-Z0-9])/g, "$1\n\n$2 ");
  const lines = normalizedSummary.split("\n");
  return lines.reduce((formattedLines, line) => {
    const previousLine = formattedLines[formattedLines.length - 1];
    if (
      line.trim()
      && BULLET_LINE_PATTERN.test(line)
      && previousLine?.trim()
    ) {
      formattedLines.push("");
    }
    formattedLines.push(line);
    return formattedLines;
  }, []).join("\n");
}
