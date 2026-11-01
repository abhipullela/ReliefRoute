// app/plan/[id]/page.tsx
// Server component shell for dynamic route /plan/[id].
// Unwraps the params Promise (Next.js 15+) and renders PlanDetailsClient.

import PlanDetailsClient from "./PlanDetailsClient";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function PlanDetailsPage({ params }: PageProps) {
  const { id } = await params;
  return <PlanDetailsClient planId={id} />;
}
