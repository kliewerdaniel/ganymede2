import { useEffect, useState } from "react";
import Head from "next/head";

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

export default function ClaimDetail({ claimId }: { claimId: string }) {
  const [data, setData] = useState<any>(null);
  const [claim, setClaim] = useState<any>(null);
  const [evidence, setEvidence] = useState<any[]>([]);

  useEffect(() => {
    fetch("/artifact.json")
      .then((r) => r.json())
      .then(setData)
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!data) return;
    const c = (data.claims || []).find((c: any) => c.id === claimId);
    setClaim(c);
    if (c?.evidence_ids) {
      const ev = (data.evidence_index || []).filter((e: any) =>
        c.evidence_ids.includes(e.id)
      );
      setEvidence(ev);
    }
  }, [data, claimId]);

  if (!data) return <div className="loading">Loading...</div>;
  if (!claim) return <div className="loading">Claim not found: {claimId}</div>;

  return (
    <>
      <Head>
        <title>{claim.text.slice(0, 60)} | Ganymede</title>
      </Head>
      <h1 style={{ marginTop: 0, fontSize: 22 }}>{claim.text}</h1>

      <div style={{ display: "flex", alignItems: "center", gap: 16, margin: "16px 0" }}>
        <StatusBadge status={claim.status} />
        <span style={{ fontSize: 14, color: "#71717a" }}>
          confidence: <strong>{(claim.confidence * 100).toFixed(0)}%</strong>
        </span>
        <span style={{ fontSize: 14, color: "#71717a" }}>
          evidence: <strong>{claim.evidence_ids?.length || 0}</strong>
        </span>
        <ConfidenceBar confidence={claim.confidence} />
      </div>

      <h3 style={{ color: "#fbbf24", fontSize: 14, marginTop: 24 }}>Confidence Terms</h3>
      <div style={{ fontSize: 12, color: "#71717a", fontFamily: "monospace", background: "var(--card)", padding: 16, borderRadius: 6 }}>
        {Object.entries(claim.confidence_terms || {}).map(([k, v]) => (
          <div key={k}>{k}: {typeof v === "number" ? v.toFixed(4) : String(v)}</div>
        ))}
      </div>

      <h3 style={{ color: "#fbbf24", fontSize: 14, marginTop: 24 }}>Evidence</h3>
      {evidence.length === 0 && <p>No evidence units linked.</p>}
      {evidence.map((e) => (
        <div key={e.id} className="card">
          <p style={{ margin: 0, fontStyle: "italic", color: "#a1a1aa" }}>"{e.quote}"</p>
          <div style={{ marginTop: 6, fontSize: 12, color: "#71717a" }}>
            stance: {e.stance} | offset: {e.offset} | source:{" "}
            <a href={`/evidence/${e.source_id}`} style={{ color: "var(--accent)" }}>
              {e.source_id}
            </a>
          </div>
        </div>
      ))}

      <h3 style={{ color: "#fbbf24", fontSize: 14, marginTop: 24 }}>Provenance</h3>
      <div style={{ fontSize: 13, color: "#71717a" }}>
        <div>source_ids: {(claim.source_ids || []).join(", ")}</div>
        <div>compiler_version: {claim.compiler_version}</div>
        <div>policy_version: {claim.policy_version}</div>
        {claim.contradiction_ids?.length > 0 && (
          <div style={{ color: "#f87171" }}>
            contradiction_ids: {claim.contradiction_ids.join(", ")}
          </div>
        )}
      </div>
    </>
  );
}
