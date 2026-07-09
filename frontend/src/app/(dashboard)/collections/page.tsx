"use client";

import Link from "next/link";
import { FolderHeart, Star } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function CollectionsPage() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-6 py-10">
      <h1 className="font-display text-[28px] font-semibold tracking-tight text-ink">
        Collections
      </h1>
      <p className="mt-2 text-base text-slate">
        Group documents into curated sets for focused research threads.
      </p>

      <div className="mt-10 rounded-3xl border border-dashed border-line bg-white/70 px-6 py-16 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-signal-soft text-signal-deep">
          <FolderHeart className="h-6 w-6" />
        </div>
        <h2 className="font-display text-xl font-semibold text-ink">
          Curate your evidence
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-slate">
          Pin related PDFs, papers, and notes into a collection, then chat against
          that subset with the same citation-backed answers.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Button className="btn-gradient rounded-xl" disabled>
            <Star className="h-4 w-4" />
            Coming soon
          </Button>
          <Button variant="outline" className="rounded-xl" asChild>
            <Link href="/documents">Browse documents</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
