import { useEffect, useState } from "react";

export default function EntityDetail({ entityId }: { entityId: string }) {
  const [data, setData] = useState<any>(null);
  const [entity, setEntity] = useState<any>(null);
  const [claims, setClaims] = useState<any[]>([]);
  const [evidence, setEvidence] = useState<any[]>([]);

  useEffect(() => {
    fetch("/artifact.json")
      .then((r) => r.json())
      .then(setData)
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!data) return;
    const e = (data.entity_index || []).find((e: any) => e.id === entityId);
    setEntity(e);
    if (e) {
      const ec = (data.claims || []).filter((c: any) => c.entity_ids?.includes(entityId));
      setClaims(ec);
      const evIds = new Set(ec.flatMap((c: any) => c.evidence_ids || []));
      const ev = (data.evidence_index || []).filter((ev: any) => evIds.has(ev.id));
      setEvidence(ev);
    }
  }, [data, entityId]);

  if (!data) return <div className="loading">Loading...</div>;
  if (!entity) return <div className="loading">Entity not found: {entityId}</div>;

  return (
    <>
      <h1 style={{ marginTop: 0 }}>{entity.name}</h1>
      <div style={{ fontSize: 13, color: "#71717a", marginBottom: 16 }}>
        type: {entity.entity_type} | mentions: {entity.mentions} | claims: {claims.length}
      </div>

      <h3 style={{ color: "#fbbf24", fontSize: 14 }}>Claims about this entity</h3>
      {claims.length === 0 && <p>No claims reference this entity.</p>}
      {claims.map((c) => (
        <div key={c.id} className="card">
          <a href={`/claims/${c.id}`} style={{ color: "var(--accent)" }}>
            {c.text}
          </a>
          <div style={{ marginTop: 4 }}>
            <span className={`badge badge-${c.status.toLowerCase()}`}>{c.status}</span>
            <span style={{ fontSize: 12, color: "#71717a", marginLeft: 8 }}>
              {(c.confidence * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      ))}

      <h3 style={{ color: "#fbbf24", fontSize: 14, marginTop: 24 }}>Evidence</h3>
      {evidence.length === 0 && <p>No evidence linked.</p>}
      {evidence.map((e) => (
        <div key={e.id} className="card">
          <p style={{ margin: 0, fontStyle: "italic", color: "#a1a1aa" }}>"{e.quote}"</p>
          <div style={{ marginTop: 6, fontSize: 12, color: "#71717a" }}>
            stance: {e.stance} | source:{" "}
            <a href={`/evidence/${e.source_id}`} style={{ color: "var(--accent)" }}>
              {e.source_id}
            </a>
          </div>
        </div>
      ))}
    </>
  );
}
