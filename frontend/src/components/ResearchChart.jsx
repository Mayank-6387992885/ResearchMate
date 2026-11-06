/*
  This component renders chart data only when the backend provides real values.
  The current /upload API returns a text summary, not structured chart data.
  Do not create research statistics from the summary text.
*/
export default function ResearchChart({ data = [] }) {
  if (!data.length) {
    return (
      <section className="panel">
        <p className="eyebrow">VISUAL INSIGHTS</p>
        <h2>Research charts</h2>
        <p className="muted">
          Charts will appear here when the analysis API returns structured,
          numerical data from the paper. No figures have been invented.
        </p>
      </section>
    );
  }

  const maxValue = Math.max(...data.map((item) => Number(item.value) || 0), 1);

  return (
    <section className="panel">
      <p className="eyebrow">VISUAL INSIGHTS</p>
      <h2>Research data</h2>
      <div className="chart-list">
        {data.map((item, index) => (
          <div className="chart-row" key={`${item.label}-${index}`}>
            <span>{item.label}</span>
            <div className="chart-track">
              <div className="chart-fill" style={{ width: `${(Number(item.value) / maxValue) * 100}%` }} />
            </div>
            <strong>{item.value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}