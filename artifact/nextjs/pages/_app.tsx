import "../styles/globals.css";
import type { AppProps } from "next/app";
import { useState } from "react";

type View = "narrative" | "claims" | "evidence" | "chronology" | "contradictions" | "provenance" | "investigations";

const VIEW_LABELS: Record<View, string> = {
  narrative: "Narrative",
  claims: "Claims",
  evidence: "Evidence",
  chronology: "Chronology",
  contradictions: "Contradictions",
  provenance: "Provenance",
  investigations: "Investigations",
};

export default function GanymedeArtifact({ Component, pageProps }: AppProps) {
  const [view, setView] = useState<View>("narrative");

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#0a0a0f", color: "#e4e4e7" }}>
      <nav style={{
        width: "240px",
        background: "#0f0f16",
        borderRight: "1px solid #1f1f2e",
        padding: "20px 0",
        position: "fixed",
        height: "100vh",
        overflowY: "auto",
      }}>
        <div style={{ padding: "0 20px 20px", borderBottom: "1px solid #1f1f2e", marginBottom: "12px" }}>
          <h1 style={{ fontSize: "18px", fontWeight: "bold", color: "#fbbf24", margin: 0 }}>Ganymede</h1>
          <p style={{ fontSize: "11px", color: "#71717a", margin: "4px 0 0" }}>Sovereign Epistemic Compiler</p>
          <p style={{ fontSize: "11px", color: "#71717a", margin: "2px 0 0" }}>Artifact v0.1.0</p>
        </div>
        {Object.entries(VIEW_LABELS).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setView(key as View)}
            style={{
              display: "block",
              width: "100%",
              padding: "10px 20px",
              textAlign: "left",
              background: view === key ? "#1f1f2e" : "transparent",
              border: "none",
              color: view === key ? "#fbbf24" : "#a1a1aa",
              fontSize: "14px",
              cursor: "pointer",
              borderLeft: view === key ? "3px solid #fbbf24" : "3px solid transparent",
              transition: "all 0.15s",
            }}
          >
            {label}
          </button>
        ))}
        <div style={{ padding: "20px", borderTop: "1px solid #1f1f2e", marginTop: "20px" }}>
          <p style={{ fontSize: "11px", color: "#71717a", margin: 0 }}>Fingerprint:</p>
          <p style={{ fontSize: "10px", color: "#52525b", margin: "4px 0 0", fontFamily: "monospace", wordBreak: "break-all" }}>
            {pageProps.artifact?.corpus_fingerprint?.slice(0, 16)}...
          </p>
        </div>
      </nav>
      <main style={{ marginLeft: "240px", flex: 1, padding: "32px 40px" }}>
        <Component {...pageProps} view={view} />
      </main>
    </div>
  );
}
