import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const reportUrl = "/dev/safety-report.json";

function App() {
  return <SafetyPage />;
}

function SafetyPage() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetch(reportUrl, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Report request failed with ${response.status}`);
        }
        return response.json();
      })
      .then((data) => {
        if (active) {
          setReport(data);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(caught.message);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const coverage = report?.ignoredPathCoverage ?? [];
  const scan = report?.secretScan ?? { status: "not-run", checkedFiles: 0, findings: {} };
  const backup = report?.backup ?? { status: "not-run", archivePath: null };
  const findingCount = useMemo(() => countFindings(scan.findings), [scan.findings]);

  return (
    <main className="page-shell">
      <section className="summary-band">
        <div>
          <p className="section-label">Local Baseline</p>
          <h1>Dev Safety</h1>
          <p className="summary-copy">Ignored-path coverage and local secret scan status from the latest JSON report.</p>
        </div>
        <StatusPill status={scan.status} />
      </section>

      {error ? <div className="alert">Could not read {reportUrl}: {error}</div> : null}

      <section className="status-grid" aria-label="Safety summary">
        <Metric title="Secret Scan" value={labelForStatus(scan.status)} tone={scan.status} />
        <Metric title="Checked Files" value={String(scan.checkedFiles ?? 0)} />
        <Metric title="Findings" value={String(findingCount)} tone={findingCount ? "failed" : "passed"} />
        <Metric title="Last Backup" value={backup.archivePath ? backup.archivePath : labelForStatus(backup.status)} tone={backup.status} />
      </section>

      <section className="panel">
        <div className="panel-heading">
          <h2>Ignored-Path Coverage</h2>
          <span>{coverage.filter((item) => item.status === "covered").length}/{coverage.length} covered</span>
        </div>
        <div className="coverage-list">
          {coverage.map((item) => (
            <article className="coverage-row" key={item.label}>
              <div>
                <h3>{item.label}</h3>
                <p>{item.gitignore?.join(", ")}</p>
              </div>
              <div className="coverage-meta">
                <span>{item.backupRule}</span>
                <StatusPill status={item.status} />
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <h2>Secret Scan</h2>
          <span>{report?.generatedAt ? new Date(report.generatedAt).toLocaleString() : "not run"}</span>
        </div>
        <FindingList findings={scan.findings} />
      </section>
    </main>
  );
}

function StatusPill({ status }) {
  return <span className={`status-pill ${status || "not-run"}`}>{labelForStatus(status)}</span>;
}

function Metric({ title, value, tone = "neutral" }) {
  return (
    <article className={`metric ${tone}`}>
      <p>{title}</p>
      <strong>{value}</strong>
    </article>
  );
}

function FindingList({ findings = {} }) {
  const groups = Object.entries(findings).filter(([, items]) => Array.isArray(items) && items.length);
  if (!groups.length) {
    return <p className="empty-state">No tracked or staged secrets found in the latest safety check.</p>;
  }

  return (
    <div className="finding-list">
      {groups.map(([title, items]) => (
        <article className="finding-group" key={title}>
          <h3>{title}</h3>
          <ul>
            {items.slice(0, 20).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      ))}
    </div>
  );
}

function countFindings(findings = {}) {
  return Object.values(findings).reduce((total, items) => total + (Array.isArray(items) ? items.length : 0), 0);
}

function labelForStatus(status) {
  if (status === "passed") return "passed";
  if (status === "failed") return "failed";
  if (status === "covered") return "covered";
  return "not run";
}

createRoot(document.getElementById("root")).render(<App />);
