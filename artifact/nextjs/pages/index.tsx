import { useEffect, useState, useMemo } from "react";
import Head from "next/head";
import { useRouter } from "next/router";

interface ArtifactIndex {
  version: string;
  compiled_at: number;
  compiler_version: string;
  policy_version: string;
  corpus_fingerprint: string;
  counts: Record<string, number>;
  status_counts: Record<string, number>;
  shards: Record<string, string[]>;
  views: { narrative: any[] };
  intermediates: { contradiction_report: string };
}

const PAGE_SIZE = 50;

const STATUS_COLORS: Record<string, string> = {
  SUPPORTED: "badge-supported",
  VALIDATED: "badge-validated",
  CONTESTED: "badge-contested",
  CONTRADICTED: "badge-contradicted",
  INSUFFICIENT: "badge-insufficient",
  UNEXAMINED: "badge-unexamined",
  RETRACTED: "badge-retracted",
  SUPERSEDED: "badge-superseded",
  UNRESOLVED: "badge-unresolved",
};

function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${STATUS_COLORS[status] || "badge-unexamined"}`}>{status}</span>;
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  return (
    <div className="confidence-bar">
      <div className="confidence-fill" style={{ width: `${(confidence || 0) * 100}%` }} />
    </div>
  );
}

function MetaLabel({ label, value }: { label: string; value: string | number | undefined }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <span className="meta-label">
      {label}: <strong>{value}</strong>
    </span>
  );
}

/** Hook: load the small artifact index. */
function useArtifactIndex() {
  const [index, setIndex] = useState<ArtifactIndex | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetch("/artifact.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setIndex)
      .catch((e) => setError(e.message));
  }, []);
  return { index, error };
}

/** Hook: lazily load and cache all shards of a kind (claims/evidence/sources...). */
function useShards(index: ArtifactIndex | null, kind: string) {
  const [items, setItems] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!index) return;
    let cancelled = false;
    const files = index.shards[kind] || [];
    Promise.all(files.map((f) => fetch(`/${f}`).then((r) => r.json())))
      .then((chunks) => {
        if (cancelled) return;
        setItems(chunks.flat());
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [index, kind]);
  return { items, error };
}

export default function Home() {
  const router = useRouter();
  const view = (router.query.view as string) || "narrative";
  const { index, error } = useArtifactIndex();

  if (error) return <div className="loading">Error loading artifact: {error}</div>;
  if (!index) return <div className="loading">Loading artifact...</div>;

  switch (view) {
    case "claims": return <ClaimsView index={index} />;
    case "evidence": return <EvidenceView index={index} />;
    case "chronology": return <ChronologyView index={index} />;
    case "contradictions": return <ContradictionsView index={index} />;
    case "provenance": return <ProvenanceView index={index} />;
    case "investigations": return <InvestigationsView index={index} />;
    case "knowledge-graph": return <KnowledgeGraphView index={index} />;
    case "narrative-doc": return <NarrativeDocView index={index} />;
    case "dossiers": return <DossiersView index={index} />;
    case "source-inventory": return <SourceInventoryView index={index} />;
    case "claim": return <ClaimDetail index={index} id={(router.query.id as string) || ""} />;
    case "source-detail": return <SourceDetail index={index} id={(router.query.id as string) || ""} />;
    default: return <NarrativeView index={index} />;
  }
}

/** Pager for large lists. */
function Pager({ page, totalPages, onPage }: { page: number; totalPages: number; onPage: (p: number) => void }) {
  if (totalPages <= 1) return null;
  const win: number[] = [];
  for (let p = Math.max(0, page - 2); p <= Math.min(totalPages - 1, page + 2); p++) win.push(p);
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 16, flexWrap: "wrap" }}>
      <button disabled={page === 0} onClick={() => onPage(page - 1)} className="pager-btn">← Prev</button>
      {win[0] > 0 && <span style={{ color: "#71717a", fontSize: 12 }}>…</span>}
      {win.map((p) => (
        <button
          key={p}
          onClick={() => onPage(p)}
          className="pager-btn"
          style={p === page ? { background: "#fbbf24", color: "#0a0a0f", borderColor: "#fbbf24" } : undefined}
        >
          {p + 1}
        </button>
      ))}
      {win[win.length - 1] < totalPages - 1 && <span style={{ color: "#71717a", fontSize: 12 }}>…</span>}
      <button disabled={page === totalPages - 1} onClick={() => onPage(page + 1)} className="pager-btn">Next →</button>
      <span style={{ color: "#71717a", fontSize: 12 }}>page {page + 1} / {totalPages}</span>
    </div>
  );
}

function NarrativeView({ index }: { index: ArtifactIndex }) {
  const narrative = index.views.narrative || [];
  return (
    <>
      <Head><title>Ganymede — Narrative</title></Head>
      <h1 style={{ marginTop: 0 }}>Narrative</h1>
      <p style={{ color: "#a1a1aa", maxWidth: 800 }}>
        What the corpus establishes — claims with SUPPORTED or VALIDATED status, ordered by confidence.
        Top {narrative.length} of {index.counts.claims.toLocaleString()} total claims.
      </p>
      <div style={{ marginTop: 24 }}>
        {narrative.length === 0 && <p>No supported claims yet.</p>}
        {narrative.map((entry: any, i: number) => (
          <div key={entry.claim_id} className="card">
            <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
              <span style={{ fontSize: 24, fontWeight: "bold", color: "#52525b", minWidth: 40 }}>{i + 1}</span>
              <div style={{ flex: 1 }}>
                <a href={`/?view=claim&id=${entry.claim_id}`} style={{ color: "#e4e4e7", fontSize: 16, textDecoration: "none" }}>
                  {entry.text}
                </a>
                <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 12 }}>
                  <StatusBadge status={entry.status} />
                  <span style={{ fontSize: 12, color: "#71717a" }}>confidence: {(entry.confidence * 100).toFixed(0)}%</span>
                  <span style={{ fontSize: 12, color: "#71717a" }}>evidence: {entry.evidence_count}</span>
                </div>
                <ConfidenceBar confidence={entry.confidence} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function ClaimsView({ index }: { index: ArtifactIndex }) {
  const { items: claims, error } = useShards(index, "claims");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    if (!claims) return [];
    return claims.filter((c: any) => {
      if (filter !== "all" && c.status !== filter) return false;
      if (search && !c.text.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [claims, filter, search]);

  useEffect(() => setPage(0), [filter, search]);

  if (error) return <div className="loading">Error loading claims: {error}</div>;
  if (!claims) return <div className="loading">Loading {index.counts.claims.toLocaleString()} claims…</div>;

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageItems = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <>
      <h1 style={{ marginTop: 0 }}>Claims</h1>
      <p style={{ color: "#a1a1aa" }}>
        All {claims.length.toLocaleString()} claims in the Epistemic Graph, filterable by status and searchable.
      </p>
      <div style={{ marginTop: 16, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <input
          type="text"
          placeholder="Search claims..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ padding: "8px 12px", background: "var(--card)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--foreground)", fontSize: 14, flex: 1, minWidth: 200 }}
        />
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ padding: "8px 12px", background: "var(--card)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--foreground)", fontSize: 14 }}
        >
          <option value="all">All statuses</option>
          {Object.keys(index.status_counts).map((s) => (
            <option key={s} value={s}>{s} ({index.status_counts[s]})</option>
          ))}
        </select>
        <span style={{ fontSize: 12, color: "#71717a" }}>{filtered.length.toLocaleString()} matches</span>
      </div>
      <div style={{ marginTop: 24 }}>
        <table>
          <thead>
            <tr><th>Status</th><th>Claim</th><th>Confidence</th><th>Evidence</th></tr>
          </thead>
          <tbody>
            {pageItems.map((c: any) => (
              <tr key={c.id}>
                <td><StatusBadge status={c.status} /></td>
                <td style={{ maxWidth: 500 }}>
                  <a href={`/?view=claim&id=${c.id}`} style={{ color: "var(--accent)" }}>{c.text}</a>
                </td>
                <td>{(c.confidence * 100).toFixed(0)}%</td>
                <td>{(c.evidence_ids || []).length}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pager page={page} totalPages={totalPages} onPage={setPage} />
      </div>
    </>
  );
}

function EvidenceView({ index }: { index: ArtifactIndex }) {
  const { items: evidence, error } = useShards(index, "evidence");
  const [page, setPage] = useState(0);

  if (error) return <div className="loading">Error loading evidence: {error}</div>;
  if (!evidence) return <div className="loading">Loading {index.counts.evidence.toLocaleString()} evidence units…</div>;

  const totalPages = Math.ceil(evidence.length / PAGE_SIZE);
  const pageItems = evidence.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <>
      <h1 style={{ marginTop: 0 }}>Evidence</h1>
      <p style={{ color: "#a1a1aa" }}>
        {evidence.length.toLocaleString()} evidence units — the smallest provenance-bearing objects.
      </p>
      <div style={{ marginTop: 24 }}>
        {pageItems.map((u: any) => (
          <div key={u.id} className="card">
            <p style={{ margin: 0, fontStyle: "italic", color: "#a1a1aa" }}>"{u.quote}"</p>
            <div style={{ marginTop: 6, fontSize: 12, color: "#71717a" }}>
              stance: {u.stance} | source:{" "}
              <a href={`/?view=source-detail&id=${u.source_id}`} style={{ color: "var(--accent)" }}>{u.source_id}</a>
              {u.timestamp ? ` | ${new Date(u.timestamp * 1000).toISOString().slice(0, 10)}` : ""}
              {u.author ? ` | ${u.author}` : ""}
            </div>
          </div>
        ))}
        <Pager page={page} totalPages={totalPages} onPage={setPage} />
      </div>
    </>
  );
}

function ChronologyView({ index }: { index: ArtifactIndex }) {
  const [timeline, setTimeline] = useState<any[] | null>(null);
  const [page, setPage] = useState(0);
  useEffect(() => {
    fetch("/data/timeline.json").then((r) => r.json()).then(setTimeline).catch(console.error);
  }, []);

  if (!timeline) return <div className="loading">Loading chronology…</div>;

  const totalPages = Math.ceil(timeline.length / PAGE_SIZE);
  const pageItems = timeline.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <>
      <h1 style={{ marginTop: 0 }}>Chronology</h1>
      <p style={{ color: "#a1a1aa" }}>
        {timeline.length.toLocaleString()} timestamped claims, earliest first.
      </p>
      <div style={{ marginTop: 24 }}>
        {pageItems.map((e: any, i: number) => (
          <div key={`${e.claim_id}-${i}`} className="card">
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: 14, fontWeight: "bold", color: "#fbbf24", minWidth: 100, fontFamily: "monospace" }}>
                {e.timestamp ? new Date(e.timestamp * 1000).toISOString().slice(0, 10) : "—"}
              </span>
              <div style={{ flex: 1 }}>
                <a href={`/?view=claim&id=${e.claim_id}`} style={{ color: "#e4e4e7" }}>{e.text}</a>
              </div>
              <StatusBadge status={e.status} />
            </div>
          </div>
        ))}
        <Pager page={page} totalPages={totalPages} onPage={setPage} />
      </div>
    </>
  );
}

function ContradictionsView({ index }: { index: ArtifactIndex }) {
  const [contras, setContras] = useState<any[] | null>(null);
  useEffect(() => {
    fetch("/data/contradictions.json").then((r) => r.json()).then(setContras).catch(console.error);
  }, []);

  if (!contras) return <div className="loading">Loading contradictions…</div>;

  return (
    <>
      <h1 style={{ marginTop: 0 }}>Contradictions</h1>
      <p style={{ color: "#a1a1aa" }}>
        {contras.length.toLocaleString()} tensions in the Epistemic Graph — both sides visible.
      </p>
      <div style={{ marginTop: 24 }}>
        {contras.length === 0 && <p>No contradictions detected.</p>}
        {contras.map((c: any) => (
          <div key={c.id} className="card">
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 16 }}>
              <div>
                <p style={{ fontSize: 12, color: "#71717a", margin: "0 0 4px" }}>Claim A</p>
                <a href={`/?view=claim&id=${c.claim_a_id}`} style={{ color: "#e4e4e7" }}>{c.text_a}</a>
              </div>
              <div style={{ display: "flex", alignItems: "center" }}>
                <span className="badge badge-contested">VS</span>
              </div>
              <div>
                <p style={{ fontSize: 12, color: "#71717a", margin: "0 0 4px" }}>Claim B</p>
                <a href={`/?view=claim&id=${c.claim_b_id}`} style={{ color: "#e4e4e7" }}>{c.text_b}</a>
              </div>
            </div>
            <div style={{ marginTop: 12, fontSize: 12, color: "#71717a" }}>
              overlap: {typeof c.overlap === "number" ? c.overlap.toFixed(2) : c.overlap} | status: {c.status}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function ProvenanceView({ index }: { index: ArtifactIndex }) {
  const { items: sources, error } = useShards(index, "sources");
  const { items: claims } = useShards(index, "claims");
  const [page, setPage] = useState(0);

  const provenance = useMemo(() => {
    if (!sources || !claims) return null;
    const claimsBySource: Record<string, number> = {};
    for (const c of claims) {
      for (const sid of c.source_ids || []) {
        claimsBySource[sid] = (claimsBySource[sid] || 0) + 1;
      }
    }
    return sources.map((s: any) => ({ ...s, claim_count: claimsBySource[s.id] || 0 }));
  }, [sources, claims]);

  if (error) return <div className="loading">Error: {error}</div>;
  if (!provenance) return <div className="loading">Loading provenance graph…</div>;

  const totalPages = Math.ceil(provenance.length / PAGE_SIZE);
  const pageItems = provenance.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <>
      <h1 style={{ marginTop: 0 }}>Provenance</h1>
      <p style={{ color: "#a1a1aa" }}>Source-to-claim traceability across {provenance.length.toLocaleString()} sources.</p>
      <div style={{ marginTop: 24 }}>
        {pageItems.map((p: any) => (
          <div key={p.id} className="card">
            <h3 style={{ color: "#fbbf24", fontSize: 14, margin: "0 0 8px" }}>
              <a href={`/?view=source-detail&id=${p.id}`} style={{ color: "var(--accent)" }}>{p.id}</a>
            </h3>
            <div style={{ fontSize: 12, color: "#71717a" }}>
              <MetaLabel label="type" value={p.source_type} />
              <MetaLabel label="author" value={p.author} />
              <MetaLabel label="claims" value={p.claim_count} />
              <MetaLabel label="fetched" value={p.fetched_at ? new Date(p.fetched_at * 1000).toISOString().slice(0, 10) : undefined} />
            </div>
            <div style={{ fontSize: 11, color: "#52525b", marginTop: 4, wordBreak: "break-all" }}>{p.origin}</div>
          </div>
        ))}
        <Pager page={page} totalPages={totalPages} onPage={setPage} />
      </div>
    </>
  );
}

function InvestigationsView({ index }: { index: ArtifactIndex }) {
  return (
    <>
      <h1 style={{ marginTop: 0 }}>Investigations</h1>
      <p style={{ color: "#a1a1aa" }}>Inquiry history and open questions.</p>
      <div style={{ marginTop: 24 }}>
        <p>No investigations yet — investigations are deliberate acts of inquiry created via the CLI.</p>
      </div>
    </>
  );
}

function KnowledgeGraphView({ index }: { index: ArtifactIndex }) {
  const [entities, setEntities] = useState<any[] | null>(null);
  const [page, setPage] = useState(0);
  useEffect(() => {
    fetch("/data/entities.json").then((r) => r.json()).then(setEntities).catch(console.error);
  }, []);

  if (!entities) return <div className="loading">Loading entities…</div>;
  const sorted = [...entities].sort((a, b) => (b.mentions || 0) - (a.mentions || 0));
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const pageItems = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <>
      <h1 style={{ marginTop: 0 }}>Knowledge Graph</h1>
      <p style={{ color: "#a1a1aa" }}>
        {entities.length.toLocaleString()} entities by mention count.
      </p>
      <div style={{ marginTop: 24 }}>
        {pageItems.map((n: any) => (
          <div key={n.id} className="card" style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ color: "var(--accent)", fontWeight: 600 }}>{n.name}</span>
            <span style={{ fontSize: 12, color: "#71717a" }}>{n.mentions} mentions</span>
            <span style={{ fontSize: 11, color: "#52525b" }}>{(n.source_ids || []).length} sources</span>
          </div>
        ))}
        <Pager page={page} totalPages={totalPages} onPage={setPage} />
      </div>
    </>
  );
}

function NarrativeDocView({ index }: { index: ArtifactIndex }) {
  const [doc, setDoc] = useState<string | null>(null);
  useEffect(() => {
    fetch("/data/narrative.md").then((r) => r.text()).then(setDoc).catch(console.error);
  }, []);
  if (doc === null) return <div className="loading">Loading narrative document…</div>;
  return (
    <>
      <h1 style={{ marginTop: 0 }}>Narrative Document</h1>
      <p style={{ color: "#a1a1aa" }}>Prose synthesis of established, contested, and insufficient-evidence claims.</p>
      <div style={{ marginTop: 24, background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, padding: 24 }}>
        <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", color: "#a1a1aa", fontSize: 14, lineHeight: 1.7 }}>{doc}</pre>
      </div>
    </>
  );
}

function DossiersView({ index }: { index: ArtifactIndex }) {
  const [entities, setEntities] = useState<any[] | null>(null);
  const { items: claims } = useShards(index, "claims");
  const [page, setPage] = useState(0);

  useEffect(() => {
    fetch("/data/entities.json").then((r) => r.json()).then(setEntities).catch(console.error);
  }, []);

  if (!entities) return <div className="loading">Loading entities…</div>;

  const sorted = [...entities].sort((a, b) => (b.mentions || 0) - (a.mentions || 0));
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const pageItems = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <>
      <h1 style={{ marginTop: 0 }}>Character Dossiers</h1>
      <p style={{ color: "#a1a1aa" }}>Per-entity summaries with claim counts.</p>
      <div style={{ marginTop: 24 }}>
        {pageItems.map((e: any) => {
          const claimCount = claims
            ? claims.filter((c: any) => (c.entity_ids || []).includes(e.id)).length
            : null;
          return (
            <div key={e.id} className="card">
              <h3 style={{ margin: "0 0 8px", fontSize: 18, color: "var(--accent)" }}>{e.name}</h3>
              <div style={{ fontSize: 12, color: "#71717a" }}>
                mentions: {e.mentions} | claims: {claimCount ?? "…"} | sources: {(e.source_ids || []).length}
              </div>
            </div>
          );
        })}
        <Pager page={page} totalPages={totalPages} onPage={setPage} />
      </div>
    </>
  );
}

function SourceInventoryView({ index }: { index: ArtifactIndex }) {
  const { items: sources, error } = useShards(index, "sources");
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!sources) return [];
    if (!search) return sources;
    return sources.filter((s: any) =>
      (s.origin || "").toLowerCase().includes(search.toLowerCase()) ||
      (s.id || "").includes(search)
    );
  }, [sources, search]);

  if (error) return <div className="loading">Error: {error}</div>;
  if (!sources) return <div className="loading">Loading {index.counts.sources.toLocaleString()} sources…</div>;

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageItems = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <>
      <h1 style={{ marginTop: 0 }}>Source Inventory</h1>
      <p style={{ color: "#a1a1aa" }}>All {sources.length.toLocaleString()} ingested sources with metadata.</p>
      <input
        type="text"
        placeholder="Search by path or ID..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ marginTop: 8, padding: "8px 12px", background: "var(--card)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--foreground)", fontSize: 14, width: "100%", maxWidth: 500 }}
      />
      <div style={{ marginTop: 24 }}>
        {pageItems.map((s: any) => (
          <div key={s.id} className="card">
            <h3 style={{ color: "#fbbf24", fontSize: 14, margin: "0 0 8px" }}>
              <a href={`/?view=source-detail&id=${s.id}`} style={{ color: "var(--accent)" }}>{s.id}</a>
            </h3>
            <div style={{ fontSize: 12, color: "#71717a" }}>
              <MetaLabel label="type" value={s.source_type} />
              <MetaLabel label="author" value={s.author} />
              <MetaLabel label="domain" value={s.domain} />
              <MetaLabel label="fetched" value={s.fetched_at ? new Date(s.fetched_at * 1000).toISOString().slice(0, 10) : undefined} />
              <MetaLabel label="parser" value={s.parser_version} />
            </div>
            <div style={{ fontSize: 11, color: "#52525b", marginTop: 4, wordBreak: "break-all" }}>{s.origin}</div>
          </div>
        ))}
        <Pager page={page} totalPages={totalPages} onPage={setPage} />
      </div>
    </>
  );
}

/** Claim detail — replaces the static /claims/[id] page at scale. */
function ClaimDetail({ index, id }: { index: ArtifactIndex; id: string }) {
  const { items: claims } = useShards(index, "claims");
  const { items: evidence } = useShards(index, "evidence");

  if (!claims) return <div className="loading">Loading claim…</div>;
  const claim = claims.find((c: any) => c.id === id);
  if (!claim) return <div className="loading">Claim not found: {id}</div>;

  const evidenceFor = evidence
    ? evidence.filter((e: any) => (claim.evidence_ids || []).includes(e.id))
    : null;

  return (
    <>
      <Head><title>{claim.text.slice(0, 60)} | Ganymede</title></Head>
      <a href="/?view=claims" style={{ color: "#71717a", fontSize: 13 }}>← All claims</a>
      <h1 style={{ marginTop: 12, fontSize: 22 }}>{claim.text}</h1>
      <div style={{ display: "flex", alignItems: "center", gap: 16, margin: "16px 0" }}>
        <StatusBadge status={claim.status} />
        <span style={{ fontSize: 14, color: "#71717a" }}>
          confidence: <strong>{(claim.confidence * 100).toFixed(0)}%</strong>
        </span>
        <span style={{ fontSize: 14, color: "#71717a" }}>
          evidence: <strong>{(claim.evidence_ids || []).length}</strong>
        </span>
        <ConfidenceBar confidence={claim.confidence} />
      </div>

      <h3 style={{ color: "#fbbf24", fontSize: 14, marginTop: 24 }}>Confidence Terms</h3>
      <div style={{ fontSize: 12, color: "#71717a", fontFamily: "monospace", background: "var(--card)", padding: 16, borderRadius: 6 }}>
        {Object.entries(claim.confidence_terms || {}).map(([k, v]) => (
          <div key={k}>{k}: {typeof v === "number" ? (v as number).toFixed(4) : String(v)}</div>
        ))}
      </div>

      <h3 style={{ color: "#fbbf24", fontSize: 14, marginTop: 24 }}>Evidence</h3>
      {!evidenceFor && <p>Loading evidence…</p>}
      {evidenceFor && evidenceFor.length === 0 && <p>No evidence units linked.</p>}
      {evidenceFor && evidenceFor.map((e: any) => (
        <div key={e.id} className="card">
          <p style={{ margin: 0, fontStyle: "italic", color: "#a1a1aa" }}>"{e.quote}"</p>
          <div style={{ marginTop: 6, fontSize: 12, color: "#71717a" }}>
            stance: {e.stance}
            {e.timestamp ? ` | ${new Date(e.timestamp * 1000).toISOString().slice(0, 10)}` : ""}
            {e.author ? ` | ${e.author}` : ""} | source:{" "}
            <a href={`/?view=source-detail&id=${e.source_id}`} style={{ color: "var(--accent)" }}>{e.source_id}</a>
          </div>
        </div>
      ))}

      <h3 style={{ color: "#fbbf24", fontSize: 14, marginTop: 24 }}>Provenance</h3>
      <div style={{ fontSize: 13, color: "#71717a" }}>
        <div>sources: {(claim.source_ids || []).length} ({(claim.source_ids || []).slice(0, 3).join(", ")}{(claim.source_ids || []).length > 3 ? " …" : ""})</div>
        <div>compiler_version: {claim.compiler_version}</div>
        <div>policy_version: {claim.policy_version}</div>
        {(claim.contradiction_ids || []).length > 0 && (
          <div style={{ color: "#f87171" }}>contradictions: {(claim.contradiction_ids || []).length}</div>
        )}
      </div>
    </>
  );
}

/** Source detail — replaces the static /evidence/[id] page at scale. */
function SourceDetail({ index, id }: { index: ArtifactIndex; id: string }) {
  const { items: sources } = useShards(index, "sources");
  const { items: evidence } = useShards(index, "evidence");
  const { items: claims } = useShards(index, "claims");

  if (!sources) return <div className="loading">Loading source…</div>;
  const source = sources.find((s: any) => s.id === id);
  if (!source) return <div className="loading">Source not found: {id}</div>;

  const evidenceFor = evidence ? evidence.filter((e: any) => e.source_id === id) : null;
  const claimsFor = claims
    ? claims.filter((c: any) => (c.source_ids || []).includes(id))
    : null;

  return (
    <>
      <Head><title>{source.id} | Ganymede</title></Head>
      <a href="/?view=source-inventory" style={{ color: "#71717a", fontSize: 13 }}>← All sources</a>
      <h1 style={{ marginTop: 12, fontSize: 20, fontFamily: "monospace" }}>{source.id}</h1>
      <div style={{ fontSize: 13, color: "#71717a", margin: "12px 0" }}>
        <div><MetaLabel label="type" value={source.source_type} /></div>
        <div><MetaLabel label="author" value={source.author} /></div>
        <div><MetaLabel label="domain" value={source.domain} /></div>
        <div><MetaLabel label="fetched" value={source.fetched_at ? new Date(source.fetched_at * 1000).toISOString().slice(0, 10) : undefined} /></div>
        <div style={{ marginTop: 4, wordBreak: "break-all" }}>{source.origin}</div>
      </div>

      <h3 style={{ color: "#fbbf24", fontSize: 14, marginTop: 24 }}>
        Claims from this source {!claimsFor ? "" : `(${claimsFor.length})`}
      </h3>
      {claimsFor && claimsFor.slice(0, 20).map((c: any) => (
        <div key={c.id} className="card" style={{ padding: 12 }}>
          <a href={`/?view=claim&id=${c.id}`} style={{ color: "#e4e4e7", fontSize: 14 }}>{c.text}</a>
          <div style={{ marginTop: 4 }}><StatusBadge status={c.status} /></div>
        </div>
      ))}
      {claimsFor && claimsFor.length > 20 && (
        <p style={{ color: "#71717a", fontSize: 12 }}>+ {claimsFor.length - 20} more claims</p>
      )}

      <h3 style={{ color: "#fbbf24", fontSize: 14, marginTop: 24 }}>
        Evidence units {!evidenceFor ? "" : `(${evidenceFor.length})`}
      </h3>
      {evidenceFor && evidenceFor.slice(0, 20).map((e: any) => (
        <div key={e.id} className="card" style={{ padding: 12 }}>
          <p style={{ margin: 0, fontStyle: "italic", color: "#a1a1aa" }}>"{e.quote}"</p>
          <div style={{ marginTop: 4, fontSize: 12, color: "#71717a" }}>stance: {e.stance} | offset: {e.offset}</div>
        </div>
      ))}
      {evidenceFor && evidenceFor.length > 20 && (
        <p style={{ color: "#71717a", fontSize: 12 }}>+ {evidenceFor.length - 20} more evidence units</p>
      )}
    </>
  );
}
