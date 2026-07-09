import Link from "next/link";
import { BrandMark } from "@/components/shared/brand";
import { Button } from "@/components/ui/button";

/*
  Landing wireframe (first viewport = one composition):
  ┌──────────────────────────────────────────────────────────┐
  │  nav: Veritas · Sign in / Get started                    │
  │                                                          │
  │           VERITAS  (hero brand)                          │
  │     Get answers, not approximations.                     │
  │     Grounded RAG with citations — not guesses.           │
  │           [ Start free ]  [ See how it works ]           │
  │                                                          │
  │     full-bleed archival document / evidence atmosphere   │
  └──────────────────────────────────────────────────────────┘
*/

export default function LandingPage() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute inset-0 veritas-grid opacity-60" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[70vh] bg-[radial-gradient(ellipse_at_center,rgb(15_159_138/0.14),transparent_60%)]" />

      <header className="relative z-10 mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5">
        <BrandMark size="sm" />
        <div className="flex items-center gap-2">
          <Button variant="ghost" asChild>
            <Link href="/login">Sign in</Link>
          </Button>
          <Button variant="signal" asChild>
            <Link href="/register">Get started</Link>
          </Button>
        </div>
      </header>

      <section className="relative z-10 mx-auto flex min-h-[calc(100vh-5rem)] w-full max-w-6xl flex-col justify-center px-6 pb-20 pt-8">
        <div className="max-w-3xl animate-rise">
          <BrandMark size="lg" className="mb-6" />
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink md:text-4xl lg:text-[2.75rem] lg:leading-[1.15]">
            Get answers, not approximations.
          </h1>
          <p className="mt-4 max-w-xl text-lg text-slate md:text-xl">
            Upload your documents. Ask anything. Every response is anchored to
            source material with clickable citations.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Button variant="signal" size="lg" asChild>
              <Link href="/register">Start free</Link>
            </Button>
            <Button variant="outline" size="lg" asChild>
              <Link href="#how">See how it works</Link>
            </Button>
          </div>
        </div>

        {/* Dominant visual plane — evidence / document atmosphere */}
        <div className="pointer-events-none absolute inset-y-8 right-[-8%] hidden w-[52%] lg:block">
          <div className="relative h-full w-full">
            <div className="absolute right-12 top-16 h-[70%] w-[78%] rotate-2 rounded-sm bg-ink shadow-lift" />
            <div className="absolute right-20 top-24 h-[70%] w-[78%] -rotate-1 overflow-hidden rounded-sm border border-line bg-white shadow-lift">
              <div className="border-b border-line bg-mist/80 px-5 py-3">
                <div className="h-2 w-24 rounded bg-line" />
              </div>
              <div className="space-y-3 p-5 font-mono text-[11px] leading-relaxed text-slate">
                <p className="text-ink">Q: What was Q3 revenue?</p>
                <p>
                  Based on the provided source material
                  <span className="citation-chip !m-0 !inline-flex">1</span>
                  , Q3 revenue was $4.2M, up 18% YoY…
                </p>
                <div className="mt-4 rounded-lg border border-signal/30 bg-signal-soft/40 p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-signal-deep">
                    Source · financials.pdf · p.12
                  </p>
                  <p className="mt-1 text-ink-soft">
                    “Total revenue for the third quarter reached $4.2 million…”
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="how" className="relative z-10 border-t border-line bg-white/60">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-20 md:grid-cols-3">
          {[
            {
              title: "Ingest with structure",
              body: "Semantic chunking, OCR for scans, and table preservation — not blind fixed-size splits.",
            },
            {
              title: "Retrieve with precision",
              body: "Hybrid vector + BM25 search, RRF fusion, HyDE, and cross-encoder reranking.",
            },
            {
              title: "Answer with evidence",
              body: "Streaming responses with inline citations you can open and verify instantly.",
            },
          ].map((item) => (
            <div key={item.title}>
              <h2 className="font-display text-xl font-semibold text-ink">
                {item.title}
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-slate">{item.body}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-line px-6 py-8 text-center text-sm text-muted-foreground">
        © {new Date().getFullYear()} Veritas · Grounded answers for serious work
      </footer>
    </div>
  );
}
