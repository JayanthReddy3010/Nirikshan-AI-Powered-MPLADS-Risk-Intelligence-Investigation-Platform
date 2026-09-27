import { useEffect, useState } from "react";
import "./App.css";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function get(path) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
async function sendAction(path, payload) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
const fmt = (value, digits = 0) =>
  value == null
    ? "—"
    : Number(value).toLocaleString("en-IN", { maximumFractionDigits: digits });
const money = (value) => (value == null ? "—" : `₹${fmt(value, 2)}`);
const percent = (value) =>
  value == null ? "—" : `${(Number(value) * 100).toFixed(1)}%`;
const idLabel = (id) => id?.replace(/^WS\//, "") || "—";
const tone = (band = "") => band.split(" ")[0].toLowerCase();

function useApi(path) {
  const [state, setState] = useState({
    loading: true,
    data: null,
    error: null,
  });
  const load = () => {
    setState({ loading: true, data: null, error: null });
    get(path)
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((error) =>
        setState({ loading: false, data: null, error: error.message }),
      );
  };
  useEffect(() => {
    let mounted = true;
    get(path)
      .then(
        (data) => mounted && setState({ loading: false, data, error: null }),
      )
      .catch(
        (error) =>
          mounted &&
          setState({ loading: false, data: null, error: error.message }),
      );
    return () => {
      mounted = false;
    };
  }, [path]);
  return { ...state, retry: load };
}
function Badge({ band, score }) {
  const label = band ? band.replace(" investigation priority", "").trim() : "Unavailable";
  return (
    <span className={`badge ${tone(band)}`}>
      {score != null ? `${Number(score).toFixed(1)} · ` : ""}
      {label}
    </span>
  );
}
function Metric({ label, value, note }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}
function Section({ eyebrow, title, children, action }) {
  return (
    <section className="panel">
      <div className="section-head">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
function Loading({ text = "Loading live analysis" }) {
  return (
    <div className="loading">
      <i />
      {text}…
    </div>
  );
}
function ErrorState({ error, retry }) {
  return (
    <div className="error">
      <b>Unable to load this view</b>
      <span>{error}</span>
      <button onClick={retry}>Retry</button>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [workId, setWorkId] = useState(null);
  const navigationItems = [
    ["dashboard", "Overview"],
    ["explorer", "Find Projects"],
    ["states", "Browse States"],
    ["vendors", "Browse MPs"],
    ["candidates", "Investigations"],
    ["dashboard", "Analytics"],
    ["dashboard", "Feedback"],
  ];
  const pageTitle =
    page === "investigation"
      ? "Investigation View"
      : page === "dashboard"
        ? "MPLADS Dashboard"
        : page === "explorer"
          ? "Find Projects"
          : page === "states"
            ? "Browse States"
            : page === "vendors"
              ? "Browse MPs"
              : page === "candidates"
                ? "Investigations"
                : "MPLADS Dashboard";
  const pageSubtitle =
    page === "dashboard"
      ? "A monitoring and analytics view of MPLADS expenditure, risk signals, and operational review priorities."
      : "Operational search and review interface for MPLADS project-level evidence and investigation prioritization.";
  const open = (id) => {
    setWorkId(id);
    setPage("investigation");
  };
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand-block">
            <div className="brand-mark">N</div>
            <div>
              <strong>Nirikshan</strong>
              <small>MPLADS Monitoring &amp; Analytics</small>
            </div>
          </div>

          <nav className="main-nav" aria-label="Main navigation">
            {navigationItems.map(([key, label], index) => (
              <button
                className={page === key ? "nav-item active" : "nav-item"}
                onClick={() => {
                  setPage(key);
                  if (key !== "investigation") setWorkId(null);
                }}
                key={`${key}-${index}`}
                type="button"
              >
                {label}
              </button>
            ))}
          </nav>

          <div className="topbar-meta">
            <label className="house-select">
              <span>House</span>
              <select defaultValue="Both Houses">
                <option>Lok Sabha</option>
                <option>Rajya Sabha</option>
                <option>Both Houses</option>
              </select>
            </label>
            <div className="status-chip">
              <span className="chip-dot" />
              Live dataset
            </div>
          </div>
        </div>
      </header>

      <main className="app-main">
        <header className="page-header">
          <div className="page-title-wrap">
            <span className="crumb">Home / MPLADS / {page === "dashboard" ? "Overview" : page === "explorer" ? "Find Projects" : page === "states" ? "Browse States" : page === "vendors" ? "Browse MPs" : page === "candidates" ? "Investigations" : "Overview"}</span>
            <h1>{pageTitle}</h1>
            <p className="page-subtitle">{pageSubtitle}</p>
          </div>
          <div className="header-status">
            <span className="chip-dot success" />
            Updated 29 Aug 2026
          </div>
        </header>
        {page === "investigation" ? (
          <Investigation workId={workId} back={() => setPage("dashboard")} />
        ) : (
          <View page={page} open={open} />
        )}
      </main>

      <footer className="app-footer">
        <div className="app-footer-inner">
          <div>
            <span className="eyebrow">Nirikshan</span>
            <strong>MPLADS Monitoring &amp; Analytics</strong>
          </div>
          <div>
            <span className="eyebrow">Data source</span>
            <p>Real MPLADS expenditure dataset</p>
          </div>
          <div>
            <span className="eyebrow">Governance</span>
            <p>Risk scores are analytical indicators for investigation prioritization, not determinations of wrongdoing.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}

function View({ page, open }) {
  if (page === "dashboard") return <Dashboard open={open} />;
  if (page === "candidates") return <Candidates open={open} />;
  if (page === "states") return <States />;
  if (page === "vendors") return <Vendors />;
  return <Explorer open={open} />;
}
function Dashboard({ open }) {
  const [filters, setFilters] = useState({
    state: "",
    risk_band: "",
    min_risk_score: "",
    max_risk_score: "",
    search: "",
  });
  const query = new URLSearchParams(
    Object.entries(filters).filter(([, value]) => value !== "" && value != null),
  );
  const summaryPath = `/api/dashboard/summary${query.toString() ? `?${query}` : ""}`;
  const distPath = `/api/dashboard/risk-distribution${query.toString() ? `?${query}` : ""}`;
  const statesPath = `/api/dashboard/state-summary${query.toString() ? `?${query}` : ""}`;
  const exposurePath = `/api/dashboard/risk-exposure${query.toString() ? `?${query}` : ""}`;
  const s = useApi(summaryPath),
    d = useApi(distPath),
    states = useApi(statesPath),
    exposure = useApi(exposurePath);
  if (s.loading || d.loading || states.loading || exposure.loading) return <Loading />;
  if (s.error || d.error || states.error || exposure.error)
    return <ErrorState error={s.error || d.error || states.error || exposure.error} retry={s.retry} />;
  const x = s.data,
    dist = d.data,
    topStates = [...states.data]
      .sort((a, b) => Number(b.total_amount) - Number(a.total_amount))
      .slice(0, 7),
    stateSummaryLabel = Object.values(filters).some((value) => value !== "") ? "Filtered operational view" : "Live operational view";
  const changeFilter = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  return (
    <div className="page">
      <div className="intro panel intro-panel">
        <div>
          <span className="eyebrow">MPLADS EXPENDITURE MONITORING</span>
          <h2>Find the signal in the spend.</h2>
          <p>Evidence-led triage for works that deserve a closer human look and a structured investigation review.</p>
          <small className="source-line">Source: Real MPLADS expenditure dataset</small>
          <small className="transparency">
            Risk scores are analytical indicators for investigation prioritization, not determinations of wrongdoing.
          </small>
        </div>
      </div>
      <div className="dashboard-filters panel">
        <div className="dashboard-filters-header">
          <span className="eyebrow">Operational filters</span>
          <strong>{stateSummaryLabel}</strong>
        </div>
        <div className="filter-grid">
          <label>
            House
            <select defaultValue="Both Houses">
              <option>Both Houses</option>
              <option>Lok Sabha</option>
              <option>Rajya Sabha</option>
            </select>
          </label>
          <label>
            Search
            <input value={filters.search} onChange={(e) => changeFilter("search", e.target.value)} placeholder="Work ID or description" />
          </label>
          <label>
            State
            <select value={filters.state} onChange={(e) => changeFilter("state", e.target.value)}>
              <option value="">All states</option>
              <option>Rajasthan</option>
              <option>Uttar Pradesh</option>
              <option>Bihar</option>
              <option>Tamil Nadu</option>
            </select>
          </label>
          <label>
            Constituency
            <input placeholder="All constituencies" />
          </label>
          <label>
            MP
            <input placeholder="All MPs" />
          </label>
          <label>
            Risk band
            <select value={filters.risk_band} onChange={(e) => changeFilter("risk_band", e.target.value)}>
              <option value="">All risk bands</option>
              <option>Low investigation priority</option>
              <option>Moderate investigation priority</option>
              <option>High investigation priority</option>
              <option>Critical investigation priority</option>
            </select>
          </label>
          <label>
            Minimum score
            <input type="number" min="0" max="100" value={filters.min_risk_score} onChange={(e) => changeFilter("min_risk_score", e.target.value)} placeholder="0" />
          </label>
          <label>
            Maximum score
            <input type="number" min="0" max="100" value={filters.max_risk_score} onChange={(e) => changeFilter("max_risk_score", e.target.value)} placeholder="100" />
          </label>
          <label>
            Period
            <select defaultValue="Current cycle">
              <option>Current cycle</option>
              <option>Annual</option>
              <option>Quarterly</option>
            </select>
          </label>
          <div className="filter-action">
            <button className="clear-filters" type="button" onClick={() => setFilters({ state: "", risk_band: "", min_risk_score: "", max_risk_score: "", search: "" })}>
              Clear filters
            </button>
          </div>
        </div>
      </div>
      <div className="stat-block">
        <div className="section-head compact-head">
          <div>
            <span className="eyebrow">General MPLADS statistics</span>
            <h2>Portfolio overview</h2>
          </div>
        </div>
        <div className="metrics">
          <Metric label="Total works" value={fmt(x.total_works)} note="Live filtered results" />
          <Metric label="Source rows" value={fmt(x.source_rows)} note="All imported rows" />
          <Metric label="Valid rows" value={fmt(x.valid_rows)} note="Rows with work IDs" />
          <Metric label="Transactions" value={fmt(x.total_transactions)} note="Database transaction records" />
          <Metric label="Total disbursed" value={money(x.total_disbursed_amount)} note="Across the live view" />
        </div>
      </div>
      <div className="stat-block">
        <div className="section-head compact-head">
          <div>
            <span className="eyebrow">Nirikshan risk monitoring</span>
            <h2>Priority signal overview</h2>
          </div>
        </div>
        <div className="metrics secondary-metrics">
          <Metric label="Import errors" value={fmt(x.import_errors)} note="Rows excluded for work ID" />
          <Metric label="Investigation candidates" value={fmt(x.investigation_candidate_count)} note="Requires investigation" />
          <Metric label="Critical priority works" value={fmt(x.critical_risk_count)} note="Score ≥ 80" />
          <Metric label="High priority works" value={fmt(x.high_risk_count)} note="Score 60–79" />
        </div>
      </div>
      <div className="dataset-scale">
        <span>Dataset scale</span>
        <b>{fmt(x.source_rows)} source rows</b>
        <b>{fmt(x.valid_rows)} valid rows</b>
        <b>{fmt(x.total_works)} works</b>
        <b>{fmt(x.total_transactions)} transactions</b>
        <b>{fmt(x.import_errors)} import error</b>
        <span className="delay-status">Delay prediction unavailable · Historical completion outcome data is unavailable in the current dataset.</span>
      </div>
      <div className="governance-panel panel">
        <span className="eyebrow">Data &amp; methodology</span>
        <ul>
          <li>Source: Real MPLADS expenditure dataset</li>
          <li>Risk scores are analytical indicators for investigation prioritization, not determinations of wrongdoing.</li>
          <li>Delay prediction is unavailable because historical completion-outcome data is not available in the current dataset.</li>
        </ul>
      </div>
      <div className="two-col">
        <Section eyebrow="PRIORITY MIX" title="Investigation priority">
          <div className="distribution">
            <div className="donut">
              <strong>{fmt(x.total_works)}</strong>
              <small>works</small>
            </div>
            <div className="legend">
              <Legend c="low" l="Low" v={dist.low_risk_count} />
              <Legend c="moderate" l="Moderate" v={dist.moderate_risk_count} />
              <Legend c="high" l="High" v={dist.high_risk_count} />
              <Legend c="critical" l="Critical" v={dist.critical_risk_count} />
            </div>
          </div>
        </Section>
        <Section eyebrow="STATE PULSE" title="Where the money moves">
          <div className="bars">
            {topStates.map((item) => (
              <div className="bar" key={item.state}>
                <span>{item.state}</span>
                <div>
                  <i
                    style={{
                      width: `${(Number(item.total_amount) / Number(topStates[0].total_amount || 1)) * 100}%`,
                    }}
                  />
                </div>
                <b>{money(item.total_amount)}</b>
              </div>
            ))}
          </div>
        </Section>
      </div>
      <Section eyebrow="FINANCIAL EXPOSURE" title="Disbursement by investigation priority">
        <div className="exposure-grid">
          {exposure.data.map((item) => {
            const share = Number(x.total_disbursed_amount || 0) === 0 ? 0 : (Number(item.total_amount) / Number(x.total_disbursed_amount)) * 100;
            return (
              <div className={`exposure-item ${tone(item.risk_band)}`} key={item.risk_band}>
                <span>{item.risk_band.replace(" investigation priority", "")}</span>
                <strong>{money(item.total_amount)}</strong>
                <small>{fmt(item.work_count)} works · {share.toFixed(1)}% of total</small>
                <i style={{ width: `${share}%` }} />
              </div>
            );
          })}
        </div>
      </Section>
      <Section eyebrow="PRIORITY QUEUE" title="Highest-risk works">
        <CandidateList items={x.top_10_highest_risk_works.slice(0, 5)} open={open} />
      </Section>
    </div>
  );
}
function Legend({ c, l, v }) {
  return (
    <div>
      <i className={c} />
      <span>{l}</span>
      <b>{fmt(v)}</b>
    </div>
  );
}
function CandidateList({ items, open }) {
  return (
    <div className="candidate-list">
      {items.map((item, i) => (
        <button
          className="candidate"
          onClick={() => open(item.work_id)}
          key={item.work_id}
        >
          <em>{String(i + 1).padStart(2, "0")}</em>
          <strong>
            {idLabel(item.work_id)}
            <small>{money(item.amount)} · investigation priority</small>
          </strong>
          <span className="indicator">Risk indicator · {item.risk_band.replace(" investigation priority", "")}</span>
          <div className="candidate-meta">
            <Badge score={item.risk_score} band={item.risk_band} />
            <span className="candidate-footnote">Requires investigation</span>
          </div>
          <b>↗</b>
        </button>
      ))}
    </div>
  );
}
function Candidates({ open }) {
  const { data, loading, error, retry } = useApi("/api/dashboard/summary");
  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} retry={retry} />;
  return (
    <div className="page">
      <div className="intro">
        <div>
          <span className="eyebrow">QUEUE / SCORE ≥ 60</span>
          <h2>Investigation candidates</h2>
          <p>
            {fmt(data.investigation_candidate_count)} works prioritized by
            combined evidence.
          </p>
        </div>
      </div>
      <Section eyebrow="PRIORITY QUEUE" title="Highest-risk works">
        <CandidateList items={data.top_10_highest_risk_works} open={open} />
      </Section>
    </div>
  );
}
function Explorer({ open }) {
  const [filters, setFilters] = useState({
    page: 1,
    page_size: 25,
    search: "",
    state: "",
    risk_band: "",
    mp_name: "",
    constituency: "",
    min_risk_score: "",
    max_risk_score: "",
  });
  const query = new URLSearchParams(
    Object.entries(filters).filter(([, v]) => v),
  );
  const { data, loading, error, retry } = useApi(`/api/works?${query}`);
  const change = (key, value) =>
    setFilters((f) => ({ ...f, [key]: value, page: 1 }));
  return (
    <div className="page">
      <div className="intro">
        <div>
          <span className="eyebrow">WORKS / 55,716 RECORDS</span>
          <h2>Works explorer</h2>
          <p>Search the live registry and open any record for evidence.</p>
        </div>
      </div>
      <Section eyebrow="LIVE REGISTRY" title="Search works">
        <div className="filters">
          <label>
            Search
            <input
              value={filters.search}
              onChange={(e) => change("search", e.target.value)}
              placeholder="Work ID or description"
            />
          </label>
          <label>
            State
            <select
              value={filters.state}
              onChange={(e) => change("state", e.target.value)}
            >
              <option value="">All states</option>
              <option>Rajasthan</option>
              <option>Uttar Pradesh</option>
              <option>Bihar</option>
              <option>Tamil Nadu</option>
            </select>
          </label>
          <label>
            MP
            <input value={filters.mp_name} onChange={(e) => change("mp_name", e.target.value)} placeholder="MP name" />
          </label>
          <label>
            Constituency
            <input value={filters.constituency} onChange={(e) => change("constituency", e.target.value)} placeholder="Constituency" />
          </label>
          <label>
            Minimum score
            <input type="number" min="0" max="100" value={filters.min_risk_score} onChange={(e) => change("min_risk_score", e.target.value)} placeholder="0" />
          </label>
          <label>
            Maximum score
            <input type="number" min="0" max="100" value={filters.max_risk_score} onChange={(e) => change("max_risk_score", e.target.value)} placeholder="100" />
          </label>
          <label>
            Priority
            <select
              value={filters.risk_band}
              onChange={(e) => change("risk_band", e.target.value)}
            >
              <option value="">All priorities</option>
              <option>Low investigation priority</option>
              <option>Moderate investigation priority</option>
              <option>High investigation priority</option>
              <option>Critical investigation priority</option>
            </select>
          </label>
          <label>
            Rows
            <select
              value={filters.page_size}
              onChange={(e) => change("page_size", e.target.value)}
            >
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </label>
        </div>
        {loading ? (
          <Loading />
        ) : error ? (
          <ErrorState error={error} retry={retry} />
        ) : (
          <>
            <div className="table-meta">
              Showing {data.items.length} of {fmt(data.total)} matching works
            </div>
            <div className="table">
              <div className="thead">
                <span>Work ID</span>
                <span>State</span>
                <span>MP / Constituency</span>
                <span>Description</span>
                <span>Priority</span>
              </div>
              {data.items.map((item) => (
                <button
                  className="tr"
                  onClick={() => open(item.work_id)}
                  key={item.work_id}
                >
                  <strong>{idLabel(item.work_id)}</strong>
                  <span>{item.state || "—"}</span>
                  <span>
                    {item.mp_name}
                    <small>{item.constituency}</small>
                  </span>
                  <span>{item.work}</span>
                  <Badge score={item.risk_score} band={item.risk_band} />
                </button>
              ))}
            </div>
            <div className="pagination">
              <button
                disabled={data.page <= 1}
                onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}
              >
                ← Previous
              </button>
              <span>Page {data.page}</span>
              <button
                disabled={data.page * data.page_size >= data.total}
                onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}
              >
                Next →
              </button>
            </div>
          </>
        )}
      </Section>
    </div>
  );
}
function States() {
  const { data, loading, error, retry } = useApi(
    "/api/dashboard/state-summary",
  );
  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} retry={retry} />;
  return (
    <SummaryTable
      title="State analysis"
      eyebrow="GEOGRAPHY / STATE"
      description="Priority-ranked spending and investigation exposure by state."
      headers={[
        "Rank",
        "State",
        "Works",
        "Total expenditure",
        "High / critical",
      ]}
      rows={[...data]
        .sort((a, b) => Number(b.total_amount) - Number(a.total_amount))
        .map((x, index) => [
          `${index + 1}`,
          x.state,
          fmt(x.work_count),
          money(x.total_amount),
          `${x.high_risk_work_count} / ${x.critical_risk_work_count}`,
        ])}
    />
  );
}
function Vendors() {
  const { data, loading, error, retry } = useApi(
    "/api/dashboard/vendor-summary",
  );
  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} retry={retry} />;
  return (
    <SummaryTable
      title="Vendor analysis"
      eyebrow="SUPPLY CHAIN / VENDORS"
      description="Spending concentration and investigation relevance across the most active vendors."
      headers={[
        "Vendor",
        "Works",
        "Transactions",
        "Total expenditure",
        "Average work amount",
        "High-risk works",
      ]}
      rows={data
        .slice(0, 50)
        .map((x) => [
          x.vendor_name,
          fmt(x.work_count),
          fmt(x.transaction_count),
          money(x.total_amount),
          money(x.average_work_amount),
          x.high_risk_work_count,
        ])}
    />
  );
}
function SummaryTable({ title, eyebrow, description, headers, rows }) {
  return (
    <div className="page">
      <div className="intro">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
      </div>
      <Section eyebrow="LIVE AGGREGATION" title="Evidence table">
        <div className="table wide">
          <div className="thead">
            {headers.map((h) => (
              <span key={h}>{h}</span>
            ))}
          </div>
          {rows.map((row, i) => (
            <div className="tr" key={i}>
              {row.map((x, j) => (
                <span className={j === 0 ? "strong" : ""} key={j}>
                  {x}
                </span>
              ))}
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

function Investigation({ workId, back }) {
  const { data, loading, error, retry } = useApi(
    `/api/works/${encodeURIComponent(workId)}`,
  );
  const [action, setAction] = useState(null);
  const [comment, setComment] = useState("");
  const [officerName, setOfficerName] = useState("");
  const [activity, setActivity] = useState([]);
  const [activityError, setActivityError] = useState(null);
  const [activityLoading, setActivityLoading] = useState(true);
  const [savingAction, setSavingAction] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);
  const [actionStatus, setActionStatus] = useState("success");

  const loadActivity = () => {
    setActivityLoading(true);
    get(`/api/works/${encodeURIComponent(workId)}/investigation-actions`)
      .then((items) => setActivity(items))
      .catch((nextError) => setActivityError(nextError.message))
      .finally(() => setActivityLoading(false));
  };

  useEffect(() => {
    let mounted = true;
    get(`/api/works/${encodeURIComponent(workId)}/investigation-actions`)
      .then((items) => mounted && setActivity(items))
      .catch((nextError) => mounted && setActivityError(nextError.message))
      .finally(() => mounted && setActivityLoading(false));
    return () => {
      mounted = false;
    };
  }, [workId]);

  const submitAction = () => {
    if (!action) return;
    setSavingAction(true);
    setActionMessage(null);
    sendAction(`/api/works/${encodeURIComponent(workId)}/investigation-actions`, {
      action,
      comment: comment.trim() || null,
      officer_name: officerName.trim() || null,
    })
      .then(() => {
        setActionStatus("success");
        setActionMessage("Investigation action saved.");
        setAction(null);
        setComment("");
        loadActivity();
      })
      .catch((nextError) => {
        setActionStatus("error");
        setActionMessage(`Unable to save action: ${nextError.message}`);
      })
      .finally(() => setSavingAction(false));
  };

  if (loading) return <Loading text="Loading investigation evidence" />;
  if (error)
    return (
      <div className="page">
        <button className="back" onClick={back}>
          ← Back
        </button>
        <ErrorState error={error} retry={retry} />
      </div>
    );

  const {
    work_information: w,
    financial_evidence: f,
    vendor_evidence: v,
    temporal_evidence: t,
    rule_evidence: rules,
    peer_evidence: p,
    ml_evidence: ml,
    composite_risk: c,
    transactions,
    delay_prediction: delay,
  } = data;

  const activityList = [...activity].sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at),
  );

  const summaryCards = [
    { label: "Total disbursed amount", value: money(f.total_disbursed_amount), note: "Financial evidence" },
    { label: "Transaction count", value: fmt(f.transaction_count), note: "Source transactions" },
    { label: "Primary vendor", value: v.primary_vendor || "—", note: v.primary_vendor_share != null ? `${percent(v.primary_vendor_share)} share` : "Vendor concentration" },
    { label: "Primary vendor share", value: v.primary_vendor_share != null ? percent(v.primary_vendor_share) : "—", note: "Transaction concentration" },
    { label: "Unique vendor count", value: fmt(v.unique_vendor_count), note: "Vendor spread" },
    { label: "Peer group size", value: fmt(p.peer_group_size), note: "Comparable works" },
    { label: "Isolation Forest score", value: ml.anomaly_score != null ? fmt(ml.anomaly_score, 1) : "—", note: ml.anomaly_label || "Anomaly indicator" },
  ];

  const evidenceGroups = [
    {
      title: "Financial signals",
      text: `The work has a total disbursed amount of ${money(f.total_disbursed_amount)} across ${fmt(f.transaction_count)} transactions. This is the core financial context for the investigation priority signal.`,
      items: [
        `Average transfer: ${money(f.average_transaction_amount)}`,
        `Largest payment: ${money(f.maximum_transaction_amount)}`,
        `Smallest payment: ${money(f.minimum_transaction_amount)}`,
      ],
    },
    {
      title: "Vendor signals",
      text: `Primary vendor concentration is ${v.primary_vendor || "not available"}. The primary vendor share is ${v.primary_vendor_share != null ? percent(v.primary_vendor_share) : "—"}, with ${fmt(v.unique_vendor_count)} unique vendors overall.`,
      items: [
        `Primary vendor: ${v.primary_vendor || "—"}`,
        `Unique vendors: ${fmt(v.unique_vendor_count)}`,
      ],
    },
    {
      title: "Transaction-pattern signals",
      text: `The work shows ${t.days_between_first_and_last_transaction != null ? `${fmt(t.days_between_first_and_last_transaction)} days` : "—"} between first and last expenditure, with an average gap of ${t.average_days_between_transactions != null ? `${fmt(t.average_days_between_transactions)} days` : "—"}.`,
      items: [
        `First expenditure: ${t.first_expenditure_date || "—"}`,
        `Latest expenditure: ${t.latest_expenditure_date || "—"}`,
      ],
    },
    {
      title: "Peer benchmark",
      text: `Peer comparison places this work against ${fmt(p.peer_group_size)} comparable works. The amount ratio to the peer median is ${p.amount_ratio_to_peer_median != null ? fmt(p.amount_ratio_to_peer_median) : "—"}, and the benchmark status is ${p.triggered ? "elevated" : "within range"}.`,
      items: [
        `Peer median: ${money(p.peer_group_median_amount)}`,
        `Peer mean: ${money(p.peer_group_mean_amount)}`,
        `Percentile rank: ${p.percentile_rank != null ? percent(p.percentile_rank) : "—"}`,
      ],
    },
    {
      title: "ML anomaly signal",
      text: `The Isolation Forest anomaly score is ${ml.anomaly_score != null ? fmt(ml.anomaly_score, 1) : "—"}. This is an unsupervised anomaly indicator used as an investigation risk signal, not proof of wrongdoing.`,
      items: [
        `Interpretation: ${ml.anomaly_label || "unsupervised anomaly indicator"}`,
        `Model: ${ml.model_name || "IsolationForest"}`,
      ],
    },
  ];

  return (
    <div className="page investigation">
      <button className="back" onClick={back}>
        ← Back to command overview
      </button>

      <div className="investigation-header">
        <div className="header-content">
          <span className="eyebrow">WORK INVESTIGATION / LIVE EVIDENCE</span>
          <h2>{w.work || w.work_id}</h2>
          <div className="work-meta-row">
            <span><strong>Work ID</strong> {w.work_id}</span>
            <span><strong>State</strong> {w.state || "—"}</span>
            <span><strong>MP</strong> {w.mp_name || "—"}</span>
            <span><strong>Constituency</strong> {w.constituency || "—"}</span>
          </div>
        </div>
        <div className="header-priority">
          <Badge score={c.final_score} band={c.risk_band} />
          <div className="investigation-priority-pill">Investigation priority</div>
        </div>
      </div>

      <div className="context">
        {[w.state, w.mp_name, w.constituency, w.ida].filter(Boolean).map((x) => (
          <span key={x}>{x}</span>
        ))}
      </div>

      <section className="risk-hero">
        <div>
          <span className="eyebrow">NIRIKSHAN RISK SCORE</span>
          <strong>
            {Number(c.final_score).toFixed(2)}
            <small>/100</small>
          </strong>
          <p>Investigation priority based on available evidence</p>
        </div>
        <div className="signals">
          <Metric label="Rule score" value={fmt(c.rule_score)} />
          <Metric label="Peer benchmark" value={fmt(c.peer_score)} />
          <Metric label="Isolation Forest" value={fmt(c.isolation_forest_score)} />
          <Metric label="Delay prediction" value="Unavailable" note={delay?.reason || "Historical completion outcome data is unavailable in the current dataset."} />
        </div>
      </section>

      <section className="panel evidence-summary-panel">
        <div className="section-head">
          <div>
            <span className="eyebrow">EVIDENCE SUMMARY</span>
            <h2>Investigation profile</h2>
          </div>
        </div>
        <div className="summary-grid">
          {summaryCards.map((item) => (
            <div className="summary-card" key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <small>{item.note}</small>
            </div>
          ))}
        </div>
      </section>

      <div className="two-col">
        <Section eyebrow="RULE EVIDENCE" title="Pattern indicators">
          <div className="rules">
            {rules.map((r) => (
              <div
                className={`rule ${r.triggered ? "triggered" : "not-triggered"}`}
                key={r.rule_id}
              >
                <div className="rule-header">
                  <div className="rule-tag-group">
                    <b>{r.rule_id}</b>
                    <strong>{r.rule_name}</strong>
                  </div>
                  <em className={r.triggered ? "triggered-state" : "not-triggered-state"}>
                    {r.triggered ? "Triggered" : "Not triggered"}
                  </em>
                </div>
                <div className="rule-metadata">
                  <span><strong>Severity</strong> {r.severity || "—"}</span>
                  <span><strong>Work ID</strong> {r.work_id || w.work_id}</span>
                </div>
                <p>{r.explanation}</p>
                <div className="rule-details">
                  <div className="rule-detail-item">
                    <span>Actual value</span>
                    <strong>
                      {(() => {
                        const values = Object.values(r.evidence_values ?? {});
                        if (values.length === 0) return "—";
                        return values
                          .map((value) =>
                            typeof value === "number"
                              ? Number(value) < 2
                                ? percent(value)
                                : fmt(value)
                              : String(value),
                          )
                          .join(" · ");
                      })()}
                    </strong>
                  </div>
                  <div className="rule-detail-item">
                    <span>Threshold</span>
                    <strong>
                      {r.threshold == null ? "—" : Number(r.threshold) < 2 ? percent(r.threshold) : fmt(r.threshold)}
                    </strong>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Section>

        <Section eyebrow="PEER BENCHMARK" title="Comparable work context">
          <div className="peer-highlight">
            <span>
              Work total <b>{money(p.actual_value)}</b>
            </span>
            <span>
              Peer median <b>{money(p.peer_group_median_amount)}</b>
            </span>
          </div>
          <div className="detail-grid">
            <Metric label="Peer level" value={p.peer_group_level?.replaceAll("_", " ") || "—"} />
            <Metric label="Peer group size" value={fmt(p.peer_group_size)} />
            <Metric label="Peer mean" value={money(p.peer_group_mean_amount)} />
            <Metric label="Standard deviation" value={money(p.peer_group_stddev)} />
            <Metric label="Amount ratio" value={p.amount_ratio_to_peer_median != null ? fmt(p.amount_ratio_to_peer_median) : "—"} />
            <Metric label="Percentile rank" value={p.percentile_rank != null ? percent(p.percentile_rank) : "—"} />
            <Metric label="Deviation" value={money(p.deviation_from_peer_median)} />
            <Metric label="Trigger status" value={p.triggered ? "Elevated" : "Within range"} />
          </div>
          <p className="note">
            Peer comparison provides investigation context and comparison against comparable works; it is not a determination of wrongdoing.
          </p>
        </Section>
      </div>

      <section className="panel">
        <div className="section-head">
          <div>
            <span className="eyebrow">EXPLAINABLE EVIDENCE</span>
            <h2>Why this work requires investigation</h2>
          </div>
        </div>
        <div className="explain-grid">
          {evidenceGroups.map((group) => (
            <div className="explain-card" key={group.title}>
              <span className="eyebrow">{group.title}</span>
              <p>{group.text}</p>
              <ul>
                {group.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <div className="two-col">
        <Section eyebrow="ISOLATION FOREST" title="Anomaly indicator">
          <div className="ml-score">
            {ml.anomaly_score != null ? fmt(ml.anomaly_score, 1) : "—"}
            <small>/100 anomaly score</small>
          </div>
          <p>
            Anomaly score is an investigation risk indicator, not proof of wrongdoing.
          </p>
          <div className="feature-grid">
            {Object.entries(ml.important_feature_values || {}).map(([k, val]) => (
              <span key={k}>
                {k.replaceAll("_", " ")}
                <b>
                  {k.includes("amount")
                    ? money(val)
                    : Number(val) < 2
                      ? percent(val)
                      : fmt(val)}
                </b>
              </span>
            ))}
          </div>
          <p className="note compact-note">
            This is an unsupervised anomaly signal produced by the model to support review and prioritization within the investigation process.
          </p>
        </Section>

        <Section eyebrow="DELAY PREDICTION" title="Availability status">
          <div className="unavailable">
            <strong>Delay prediction unavailable</strong>
            <p>Historical completion outcome data is unavailable in the current dataset.</p>
          </div>
        </Section>
      </div>

      <Section eyebrow="TRANSACTION HISTORY" title={`${fmt(transactions.total)} source transactions`}>
        <div className="table transactions">
          <div className="thead">
            <span>Expenditure date</span>
            <span>Vendor</span>
            <span>Payment status</span>
            <span>Amount</span>
            <span>Source row / reference</span>
          </div>
          {transactions.items.map((x) => (
            <div className="tr" key={x.source_row_number}>
              <span>{x.expenditure_date || "—"}</span>
              <strong>{x.vendor_name || "—"}</strong>
              <span className="status-pill">{x.payment_status || "—"}</span>
              <span>{money(x.fund_disbursed_amount)}</span>
              <span>#{x.source_row_number}</span>
            </div>
          ))}
        </div>
      </Section>

      <div className="action-panel panel">
        <div className="action-copy">
          <span className="eyebrow">OFFICER WORKSPACE</span>
          <h3>Why is this work prioritized?</h3>
          <p>
            {c.explanation} Delay prediction is not included because historical completion outcomes are unavailable.
          </p>
          <small>Actions are recorded as investigation activity and do not change evidence, scoring, or risk logic.</small>
        </div>

        <div className="action-form">
          <label>
            Officer name
            <input
              value={officerName}
              onChange={(event) => setOfficerName(event.target.value)}
              placeholder="Optional"
            />
          </label>
          <label>
            Comment
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="Optional investigation note"
              rows="2"
            />
          </label>

          <div className="action-buttons">
            {[
              "Reviewed",
              "Request Documents",
              "Escalate",
              "Close Investigation",
            ].map((option) => (
              <button
                key={option}
                className={action === option ? "chosen" : ""}
                onClick={() => setAction(option)}
              >
                {option}
              </button>
            ))}
          </div>

          {action && (
            <div className="confirm-action">
              <span>Confirm: {action}?</span>
              <button onClick={submitAction} disabled={savingAction}>
                {savingAction ? "Saving…" : "Confirm action"}
              </button>
              <button onClick={() => setAction(null)} disabled={savingAction}>
                Cancel
              </button>
            </div>
          )}

          {actionMessage && (
            <small className={`action-message ${actionStatus}`}>{actionMessage}</small>
          )}
        </div>
      </div>

      <Section eyebrow="INVESTIGATION ACTIVITY" title="Officer action history">
        {activityLoading ? (
          <Loading text="Loading activity" />
        ) : activityError ? (
          <ErrorState error={activityError} retry={loadActivity} />
        ) : activityList.length === 0 ? (
          <p className="note">No investigation actions recorded yet.</p>
        ) : (
          <div className="activity-list">
            {activityList.map((item) => (
              <div className="activity-item" key={item.id}>
                <div className="activity-head">
                  <strong>{item.action}</strong>
                  <span>{item.officer_name || "Officer not specified"}</span>
                </div>
                <time>{new Date(item.created_at).toLocaleString()}</time>
                {item.comment && <p>{item.comment}</p>}
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
