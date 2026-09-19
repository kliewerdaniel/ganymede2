import { useEffect, useState } from "react";

interface ArtifactData {
  version: string;
  compiled_at: number;
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

function NarrativeView({ views }: { views: any }) {
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

function ClaimsView({ views }: { views: any }) {
  return (
    <>
      <h1 style={{ marginTop: 0 }}>Claims</h1>
      <p style={{ color: "#a1a1aa" }}>All claims in the Epistemic Graph, filterable by status and confidence.</p>
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
            {views.claims.map((c: any) => (
              <tr key={c.claim_id}>
                <td><StatusBadge status={c.status} /></td>
                <td style={{ maxWidth: 500 }}>{c.text}</td>
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
        {views.evidence.map((group: any) => (
          <div key={group.source_id} style={{ marginBottom: 24 }}>
            <h3 style={{ color: "#fbbf24", fontSize: 14 }}>{group.source_id}</h3>
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

function ChronologyView({ views }: { views: any }) {
  return (
    <>
      <h1 style={{ marginTop: 0 }}>Chronology</h1>
      <p style={{ color: "#a1a1aa" }}>Temporal ordering of events.</p>
      <div style={{ marginTop: 24 }}>
        {views.chronology.length === 0 && <p>No temporal data available.</p>}
        {views.chronology.map((e: any, i: number) => (
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

function ContradictionsView({ views }: { views: any }) {
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
            <h3 style={{ color: "#fbbf24", fontSize: 14, margin: "0 0 8px" }}>{p.source_id}</h3>
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

export default function Home({ view }: { view: string }) {
  const [data, setData] = useState<ArtifactData | null>(null);

  useEffect(() => {
    fetch("/artifact.json")
      .then((r) => r.json())
      .then(setData)
      .catch(console.error);
  }, []);

  if (!data) return <div style={{ padding: 40 }}>Loading artifact...</div>;

  const viewProps = { views: data.views };

  switch (view) {
    case "claims": return <ClaimsView {...viewProps} />;
    case "evidence": return <EvidenceView {...viewProps} />;
    case "chronology": return <ChronologyView {...viewProps} />;
    case "contradictions": return <ContradictionsView {...viewProps} />;
    case "provenance": return <ProvenanceView {...viewProps} />;
    case "investigations": return <InvestigationsView {...viewProps} />;
    default: return <NarrativeView {...viewProps} />;
  }
}
