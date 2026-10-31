// app/dashboard/[planId]/page.tsx
// Server component shell — resolves params and delegates to the client dashboard.
// Next.js 15: params is a Promise; resolve it here (server-side) and pass as a prop.
import DashboardClient from "./DashboardClient";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ planId: string }>;
}

export default async function DashboardPage({ params }: PageProps) {
  const { planId } = await params;
  return <DashboardClient planId={planId} />;
}
