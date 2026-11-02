// app/plan/[id]/page.tsx
// Server component shell for dynamic route /plan/[id].
// Unwraps the params Promise (Next.js 15+) and renders PlanDetailsClient inside Suspense.

import React, { Suspense } from "react";
import PlanDetailsClient from "./PlanDetailsClient";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function PlanDetailsPage({ params }: PageProps) {
  const { id } = await params;
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
          <div className="h-8 w-8 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      }
    >
      <PlanDetailsClient planId={id} />
    </Suspense>
  );
}
