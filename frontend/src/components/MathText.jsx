import katex from "katex";

const MATH_TOKEN_REGEX =
  /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|(?<!\\)\$[^$\n]+?(?<!\\)\$)/g;

/**
 * Renders plain text interspersed with inline ($...$, \(...\)) and
 * display ($$...$$, \[...\]) LaTeX math expressions using KaTeX.
 */
export default function MathText({ text }) {
  if (typeof text !== "string" || text.length === 0) {
    return null;
  }

  const parts = [];
  let lastIndex = 0;
  let match;

  MATH_TOKEN_REGEX.lastIndex = 0;
  while ((match = MATH_TOKEN_REGEX.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    let expr = "";
    let displayMode = false;

    if (token.startsWith("$$") && token.endsWith("$$")) {
      expr = token.slice(2, -2).trim();
      displayMode = true;
    } else if (token.startsWith("\\[") && token.endsWith("\\]")) {
      expr = token.slice(2, -2).trim();
      displayMode = true;
    } else if (token.startsWith("\\(") && token.endsWith("\\)")) {
      expr = token.slice(2, -2).trim();
      displayMode = false;
    } else if (token.startsWith("$") && token.endsWith("$")) {
      expr = token.slice(1, -1).trim();
      displayMode = false;
    }

    const html = katex.renderToString(expr, {
      displayMode,
      throwOnError: false,
    });

    parts.push(
      <span
        key={`math-${match.index}`}
        className={displayMode ? "math-display" : "math-inline"}
        dangerouslySetInnerHTML={{ __html: html }}
      />,
    );

    lastIndex = MATH_TOKEN_REGEX.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return <>{parts}</>;
}
