import { useEffect, useState } from "react";
import Head from "next/head";

interface ArtifactData {
  version: string;
  compiled_at: number;
  compiler_version: string;
  policy_version: string;
  corpus_fingerprint: string;
  claims: any[];
  evidence_index: any[];
  entity_index: any[];
  contradictions: any[];
  investigations: any[];
  provenance_index: any[];
  views: any;
  intermediates: any;
}

const STATUS_COLORS: Record<string, string> = {
  SUPPORTED: "badge-supported",
  VALIDATED: "badge-validated",
  CONTESTED: "badge-contested",
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

export default function Home({ view }: { view: string }) {
  const [data, setData] = useState<ArtifactData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/artifact.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="loading">Error loading artifact: {error}</div>;
  if (!data) return <div className="loading">Loading artifact...</div>;

  const viewProps = { views: data.views, data };

  switch (view) {
    case "claims": return <ClaimsView {...viewProps} />;
    case "evidence": return <EvidenceView {...viewProps} />;
    case "chronology": return <ChronologyView {...viewProps} />;
    case "contradictions": return <ContradictionsView {...viewProps} />;
    case "provenance": return <ProvenanceView {...viewProps} />;
    case "investigations": return <InvestigationsView {...viewProps} />;
    case "knowledge-graph": return <KnowledgeGraphView {...viewProps} />;
    case "narrative-doc": return <NarrativeDocView {...viewProps} />;
    case "dossiers": return <DossiersView {...viewProps} />;
    case "source-inventory": return <SourceInventoryView {...viewProps} />;
    default: return <NarrativeView {...viewProps} />;
  }
}

function NarrativeView({ views, data }: { views: any; data: ArtifactData }) {
  const narrative = data.intermediates?.narrative_document;
  return (
    <>
      <h1 style={{ marginTop: 0 }}>Narrative</h1>
      <p style={{ color: "#a1a1aa", maxWidth: 800 }}>
        What Ganymede establishes — claims with SUPPORTED or VALIDATED status, ordered by confidence.
      </p>
      <div style={{ marginTop: 24 }}>
        {views.narrative.length === 0 && <p>No supported claims yet.</p>}
        {views.narrative.map((entry: any, i: number) => (
          <div key={entry.claim_id} className="card">
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: 24, fontWeight: "bold", color: "#52525b" }}>{i + 1}</span>
              <div style={{ flex: 1 }}>
                <p style={{ margin: 0, fontSize: 16, color: "#e4e4e7" }}>{entry.text}</p>
                <div style={{ marginTop: 6, display: "flex", alignItems: "center", gap: 12 }}>
                  <StatusBadge status={entry.status} />
                  <span style={{ fontSize: 12, color: "#71717a" }}>
                    confidence: {(entry.confidence * 100).toFixed(0)}%
                  </span>
                  <span style={{ fontSize: 12, color: "#71717a" }}>
                    evidence: {entry.evidence_ids?.length || 0}
                  </span>
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

function ClaimsView({ views, data }: { views: any; data: ArtifactData }) {
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState<string>("");

  const claims: any[] = views.claims || [];
  const filtered = claims.filter((c: any) => {
    if (filter !== "all" && c.status !== filter) return false;
    if (search && !c.text.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const statuses: string[] = [...new Set(claims.map((c: any) => c.status as string))];

  return (
    <>
      <h1 style={{ marginTop: 0 }}>Claims</h1>
      <p style={{ color: "#a1a1aa" }}>All claims in the Epistemic Graph, filterable by status and searchable.</p>

      <div style={{ marginTop: 16, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <input
          type="text"
          placeholder="Search claims..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            padding: "8px 12px",
            background: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            color: "var(--foreground)",
            fontSize: 14,
            flex: 1,
            minWidth: 200,
          }}
        />
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{
            padding: "8px 12px",
            background: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            color: "var(--foreground)",
            fontSize: 14,
          }}
        >
          <option value="all">All statuses</option>
          {statuses.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <span style={{ fontSize: 12, color: "#71717a" }}>{filtered.length} of {claims.length}</span>
      </div>

      <div style={{ marginTop: 24 }}>
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Claim</th>
              <th>Confidence</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((c: any) => (
              <tr key={c.claim_id}>
                <td><StatusBadge status={c.status} /></td>
                <td style={{ maxWidth: 500 }}>
                  <a href={`/claims/${c.claim_id}`} style={{ color: "var(--accent)" }}>
                    {c.text}
                  </a>
                </td>
                <td>{(c.confidence * 100).toFixed(0)}%</td>
                <td>{c.evidence_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function EvidenceView({ views }: { views: any }) {
  return (
    <>
      <h1 style={{ marginTop: 0 }}>Evidence</h1>
      <p style={{ color: "#a1a1aa" }}>Evidence units grouped by source.</p>
      <div style={{ marginTop: 24 }}>
        {views.evidence.length === 0 && <p>No evidence units.</p>}
        {views.evidence.map((group: any) => (
          <div key={group.source_id} style={{ marginBottom: 24 }}>
            <h3 style={{ color: "#fbbf24", fontSize: 14 }}>
              <a href={`/evidence/${group.source_id}`} style={{ color: "var(--accent)" }}>
                {group.source_id}
              </a>
            </h3>
            {group.units.map((u: any) => (
              <div key={u.evidence_id} className="card">
                <p style={{ margin: 0, fontStyle: "italic", color: "#a1a1aa" }}>"{u.quote}"</p>
                <div style={{ marginTop: 6, fontSize: 12, color: "#71717a" }}>
                  stance: {u.stance} | offset: {u.offset}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  );
}

function ChronologyView({ views, data }: { views: any; data: ArtifactData }) {
  const timeline = data.intermediates?.timeline || views.chronology || [];
  return (
    <>
      <h1 style={{ marginTop: 0 }}>Chronology</h1>
      <p style={{ color: "#a1a1aa" }}>Temporal ordering of events.</p>
      <div style={{ marginTop: 24 }}>
        {timeline.length === 0 && <p>No temporal data available.</p>}
        {timeline.map((e: any, i: number) => (
          <div key={e.claim_id} className="card">
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: 20, fontWeight: "bold", color: "#52525b" }}>{i + 1}</span>
              <div style={{ flex: 1 }}>
                <p style={{ margin: 0 }}>{e.text}</p>
                <div style={{ fontSize: 12, color: "#71717a", marginTop: 4 }}>
                  {e.timestamp ? new Date(e.timestamp * 1000).toISOString() : "no timestamp"}
                </div>
              </div>
              <StatusBadge status={e.status} />
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function ContradictionsView({ views, data }: { views: any; data: ArtifactData }) {
  const report = data.intermediates?.contradiction_report;
  return (
    <>
      <h1 style={{ marginTop: 0 }}>Contradictions</h1>
      <p style={{ color: "#a1a1aa" }}>Tensions in the Epistemic Graph — both sides visible.</p>
      <div style={{ marginTop: 24 }}>
        {views.contradictions.length === 0 && <p>No contradictions detected.</p>}
        {views.contradictions.map((c: any) => (
          <div key={c.contradiction_id} className="card">
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 16 }}>
              <div>
                <p style={{ fontSize: 12, color: "#71717a", margin: "0 0 4px" }}>Claim A</p>
                <p style={{ margin: 0 }}>{c.text_a}</p>
              </div>
              <div style={{ display: "flex", alignItems: "center" }}>
                <span className="badge badge-contested">VS</span>
              </div>
              <div>
                <p style={{ fontSize: 12, color: "#71717a", margin: "0 0 4px" }}>Claim B</p>
                <p style={{ margin: 0 }}>{c.text_b}</p>
              </div>
            </div>
            <div style={{ marginTop: 12, fontSize: 12, color: "#71717a" }}>
              overlap: {c.overlap.toFixed(2)} | status: {c.status}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function ProvenanceView({ views }: { views: any }) {
  return (
    <>
      <h1 style={{ marginTop: 0 }}>Provenance</h1>
      <p style={{ color: "#a1a1aa" }}>Source-to-claim traceability graph.</p>
      <div style={{ marginTop: 24 }}>
        {views.provenance.map((p: any) => (
          <div key={p.source_id} className="card">
            <h3 style={{ color: "#fbbf24", fontSize: 14, margin: "0 0 8px" }}>
              <a href={`/evidence/${p.source_id}`} style={{ color: "var(--accent)" }}>
                {p.source_id}
              </a>
            </h3>
            <p style={{ fontSize: 12, color: "#71717a", margin: "0 0 8px" }}>type: {p.source_type}</p>
            <p style={{ fontSize: 12, color: "#71717a", margin: 0 }}>
              {p.claim_ids.length} claim(s): {p.claim_ids.slice(0, 3).join(", ")}
              {p.claim_ids.length > 3 && ` (+${p.claim_ids.length - 3} more)`}
            </p>
          </div>
        ))}
      </div>
    </>
  );
}

function InvestigationsView({ views }: { views: any }) {
  return (
    <>
      <h1 style={{ marginTop: 0 }}>Investigations</h1>
      <p style={{ color: "#a1a1aa" }}>Inquiry history and open questions.</p>
      <div style={{ marginTop: 24 }}>
        {views.investigations.length === 0 && <p>No investigations yet.</p>}
        {views.investigations.map((inv: any) => (
          <div key={inv.investigation_id} className="card">
            <h3 style={{ margin: "0 0 8px", fontSize: 16 }}>{inv.question}</h3>
            <div style={{ fontSize: 12, color: "#71717a" }}>
              status: {inv.status} | claims: {inv.claim_ids?.length || 0}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function KnowledgeGraphView({ data }: { data: ArtifactData }) {
  const kg = data.intermediates?.knowledge_graph;
  const nodes = kg?.nodes || [];
  const links = kg?.links || [];

  return (
    <>
      <h1 style={{ marginTop: 0 }}>Knowledge Graph</h1>
      <p style={{ color: "#a1a1aa" }}>Entity-claim relationship graph (d3.js-compatible JSON).</p>
      <div style={{ marginTop: 16, fontSize: 13, color: "#71717a" }}>
        {nodes.length} nodes, {links.length} links
      </div>
      <div style={{ marginTop: 24 }}>
        <h3 style={{ color: "#fbbf24", fontSize: 14 }}>Entities</h3>
        {nodes.filter((n: any) => n.type === "entity").length === 0 && (
          <p>No entities extracted yet.</p>
        )}
        {nodes.filter((n: any) => n.type === "entity").map((n: any) => (
          <div key={n.id} className="card">
            <a href={`/entities/${n.id}`} style={{ color: "var(--accent)", fontWeight: 600 }}>
              {n.name}
            </a>
            <span style={{ fontSize: 12, color: "#71717a", marginLeft: 8 }}>
              {n.mentions} mentions
            </span>
          </div>
        ))}

        <h3 style={{ color: "#fbbf24", fontSize: 14, marginTop: 24 }}>Claims</h3>
        {nodes.filter((n: any) => n.type === "claim").slice(0, 20).map((n: any) => (
          <div key={n.id} className="card">
            <a href={`/claims/${n.id}`} style={{ color: "#e4e4e7" }}>
              {n.text}
            </a>
            <div style={{ marginTop: 4 }}>
              <StatusBadge status={n.status} />
              <span style={{ fontSize: 12, color: "#71717a", marginLeft: 8 }}>
                {(n.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function NarrativeDocView({ data }: { data: ArtifactData }) {
  const narrative = data.intermediates?.narrative_document || "No narrative available.";
  return (
    <>
      <h1 style={{ marginTop: 0 }}>Narrative Document</h1>
      <p style={{ color: "#a1a1aa" }}>Prose synthesis of established, contested, and insufficient-evidence claims.</p>
      <div style={{ marginTop: 24, background: "var(--card)", border: "1px solid var(--border)", borderRadius: 8, padding: 24 }}>
        <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", color: "#a1a1aa", fontSize: 14, lineHeight: 1.7 }}>
          {narrative}
        </pre>
      </div>
    </>
  );
}

function DossiersView({ data }: { data: ArtifactData }) {
  const dossiers = data.intermediates?.character_dossiers || {};
  const entries = Object.entries(dossiers);

  return (
    <>
      <h1 style={{ marginTop: 0 }}>Character Dossiers</h1>
      <p style={{ color: "#a1a1aa" }}>Per-entity summaries with claims and evidence.</p>
      <div style={{ marginTop: 24 }}>
        {entries.length === 0 && <p>No character dossiers available.</p>}
        {entries.map(([entityId, dossier]: [string, any]) => (
          <div key={entityId} className="card">
            <h3 style={{ margin: "0 0 8px", fontSize: 18 }}>
              <a href={`/entities/${entityId}`} style={{ color: "var(--accent)" }}>
                {dossier.name}
              </a>
            </h3>
            <div style={{ fontSize: 12, color: "#71717a", marginBottom: 12 }}>
              type: {dossier.entity_type} | mentions: {dossier.mentions} | claims: {dossier.claims?.length || 0}
            </div>
            {dossier.claims?.slice(0, 3).map((c: any) => (
              <div key={c.claim_id} style={{ marginBottom: 8, paddingLeft: 12, borderLeft: "2px solid var(--border)" }}>
                <a href={`/claims/${c.claim_id}`} style={{ color: "#e4e4e7", fontSize: 14 }}>
                  {c.text}
                </a>
                <div style={{ marginTop: 2 }}>
                  <StatusBadge status={c.status} />
                  <span style={{ fontSize: 11, color: "#71717a", marginLeft: 8 }}>
                    {(c.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            ))}
            {dossier.claims?.length > 3 && (
              <div style={{ fontSize: 12, color: "#71717a", marginTop: 8 }}>
                +{dossier.claims.length - 3} more claims
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

function SourceInventoryView({ data }: { data: ArtifactData }) {
  const sources = data.intermediates?.source_inventory || [];
  return (
    <>
      <h1 style={{ marginTop: 0 }}>Source Inventory</h1>
      <p style={{ color: "#a1a1aa" }}>All ingested sources with metadata.</p>
      <div style={{ marginTop: 24 }}>
        {sources.length === 0 && <p>No sources ingested.</p>}
        {sources.map((s: any) => (
          <div key={s.source_id} className="card">
            <h3 style={{ color: "#fbbf24", fontSize: 14, margin: "0 0 8px" }}>
              <a href={`/evidence/${s.source_id}`} style={{ color: "var(--accent)" }}>
                {s.source_id}
              </a>
            </h3>
            <div style={{ fontSize: 12, color: "#71717a" }}>
              <MetaLabel label="type" value={s.type} />
              <MetaLabel label="origin" value={s.origin} />
              <MetaLabel label="domain" value={s.domain} />
              <MetaLabel label="author" value={s.author} />
              <MetaLabel label="parser" value={s.parser_version} />
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
