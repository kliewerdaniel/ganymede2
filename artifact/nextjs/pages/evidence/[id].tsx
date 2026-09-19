import { useEffect, useState } from "react";
import Head from "next/head";
import fs from "fs";
import path from "path";

export function getStaticPaths() {
  const artifactPath = path.join(process.cwd(), "public", "artifact.json");
  const data = JSON.parse(fs.readFileSync(artifactPath, "utf-8"));
  const paths = (data.views?.evidence || []).map((g: any) => ({
    params: { id: String(g.source_id) },
  }));
  return { paths, fallback: false };
}

export function getStaticProps({ params }: { params: { id: string } }) {
  return { props: { sourceId: params.id } };
}

export default function EvidenceDetail({ sourceId }: { sourceId: string }) {
  const [data, setData] = useState<any>(null);
  const [source, setSource] = useState<any>(null);
  const [claims, setClaims] = useState<any[]>([]);

  useEffect(() => {
    fetch("/artifact.json")
      .then((r) => r.json())
      .then(setData)
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!data) return;
    const group = (data.views?.evidence || []).find((g: any) => g.source_id === sourceId);
    setSource(group);
    if (group?.units) {
      const related = (data.claims || []).filter((c: any) =>
        group.units.some((u: any) => u.claim_id === c.id)
      );
      setClaims(related);
    }
  }, [data, sourceId]);

  if (!data) return <div className="loading">Loading...</div>;
  if (!source) return <div className="loading">Source not found: {sourceId}</div>;

  return (
    <>
      <Head>
        <title>{sourceId} | Ganymede</title>
      </Head>
      <h1 style={{ marginTop: 0 }}>{sourceId}</h1>
      <p style={{ color: "#a1a1aa" }}>{source.units.length} evidence unit(s)</p>

      <h3 style={{ color: "#fbbf24", fontSize: 14, marginTop: 24 }}>Evidence Units</h3>
      {source.units.map((u: any) => (
        <div key={u.evidence_id} className="card">
          <p style={{ margin: 0, fontStyle: "italic", color: "#a1a1aa" }}>"{u.quote}"</p>
          <div style={{ marginTop: 6, fontSize: 12, color: "#71717a" }}>
            stance: {u.stance} | offset: {u.offset}
          </div>
        </div>
      ))}

      <h3 style={{ color: "#fbbf24", fontSize: 14, marginTop: 24 }}>Related Claims</h3>
      {claims.length === 0 && <p>No claims linked to this source.</p>}
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
    </>
  );
}
