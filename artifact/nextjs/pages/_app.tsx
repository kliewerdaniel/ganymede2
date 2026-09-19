import type { AppProps } from "next/app";
import Link from "next/link";
import { useRouter } from "next/router";
import "../styles/globals.css";

const NAV_LINKS = [
  { href: "/", label: "Narrative" },
  { href: "/?view=claims", label: "Claims" },
  { href: "/?view=evidence", label: "Evidence" },
  { href: "/?view=chronology", label: "Chronology" },
  { href: "/?view=contradictions", label: "Contradictions" },
  { href: "/?view=provenance", label: "Provenance" },
  { href: "/?view=investigations", label: "Investigations" },
  { href: "/?view=knowledge-graph", label: "Knowledge Graph" },
  { href: "/?view=narrative-doc", label: "Narrative Doc" },
  { href: "/?view=dossiers", label: "Dossiers" },
  { href: "/?view=source-inventory", label: "Sources" },
];

export default function GanymedeArtifact({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const currentPath = router.asPath;

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#0a0a0f", color: "#e4e4e7" }}>
      <nav
        style={{
          width: 200,
          background: "#0f0f16",
          borderRight: "1px solid #1f1f2e",
          padding: "20px 0",
          position: "fixed",
          top: 0,
          left: 0,
          bottom: 0,
          overflowY: "auto",
        }}
      >
        <div
          style={{
            padding: "0 20px 16px",
            borderBottom: "1px solid #1f1f2e",
            marginBottom: 12,
          }}
        >
          <Link
            href="/"
            style={{
              color: "#fbbf24",
              fontWeight: 700,
              fontSize: 16,
              textDecoration: "none",
            }}
          >
            Ganymede
          </Link>
          <div style={{ fontSize: 11, color: "#52525b", marginTop: 4 }}>
            Sovereign Epistemic Compiler
          </div>
          <div style={{ fontSize: 11, color: "#52525b", marginTop: 2 }}>
            Artifact v0.1.0
          </div>
        </div>
        {NAV_LINKS.map((link) => {
          const isActive =
            link.href === "/"
              ? currentPath === "/"
              : currentPath.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              style={{
                display: "block",
                padding: "8px 20px",
                color: isActive ? "#fbbf24" : "#a1a1aa",
                fontSize: 13,
                textDecoration: "none",
                borderLeft: isActive
                  ? "3px solid #fbbf24"
                  : "3px solid transparent",
              }}
            >
              {link.label}
            </Link>
          );
        })}
        <div style={{ padding: "20px", borderTop: "1px solid #1f1f2e", marginTop: 20 }}>
          <p style={{ fontSize: 11, color: "#71717a", margin: 0 }}>Fingerprint:</p>
          <p style={{ fontSize: 10, color: "#52525b", margin: "4px 0 0", fontFamily: "monospace", wordBreak: "break-all" }}>
            {pageProps.artifact?.corpus_fingerprint?.slice(0, 16)}...
          </p>
        </div>
      </nav>
      <main
        style={{
          marginLeft: 200,
          padding: "32px 40px",
          flex: 1,
          maxWidth: 1000,
        }}
      >
        <Component {...pageProps} />
      </main>
    </div>
  );
}
