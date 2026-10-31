"use client";
// app/dashboard/[planId]/DashboardClient.tsx
// The full client-side operator dashboard.
// Receives planId from the server page component (params already resolved).

import React, { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import {
  RefreshCw,
  AlertTriangle,
  Radio,
  Loader2,
  Activity,
} from "lucide-react";
import type { DeliveryPlan, DispatchResult } from "@/app/types/api";
import { getPlan } from "@/app/lib/api";
import type { ApiError } from "@/app/lib/api";
import ApprovalPanel from "@/app/components/ApprovalPanel";
import DispatchPanel from "@/app/components/DispatchPanel";
import AuditTrail from "@/app/components/AuditTrail";
import { useApiErrorToast } from "@/app/components/Toast";

// MapView uses maplibre-gl which is browser-only; SSR must be disabled.
const MapView = dynamic(() => import("@/app/components/MapView"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full bg-slate-900/60 rounded-xl">
      <div className="flex flex-col items-center gap-3 text-slate-500">
        <Loader2 className="h-8 w-8 animate-spin" />
        <p className="text-sm font-medium">Loading map…</p>
      </div>
    </div>
  ),
});

// -------------------------------------------------------------------------
// Loading skeleton
// -------------------------------------------------------------------------

function LoadingSkeleton() {
  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-100 p-4 gap-4 animate-pulse">
      <div className="h-14 bg-slate-900/60 rounded-2xl" />
      <div className="flex-1 grid grid-cols-[1fr_360px] gap-4">
        <div className="bg-slate-900/60 rounded-2xl" />
        <div className="flex flex-col gap-4">
          <div className="h-[55%] bg-slate-900/60 rounded-2xl" />
          <div className="h-[45%] bg-slate-900/60 rounded-2xl" />
        </div>
      </div>
      <div className="h-52 bg-slate-900/60 rounded-2xl" />
    </div>
  );
}

// -------------------------------------------------------------------------
// Status indicator
// -------------------------------------------------------------------------

const STATUS_PULSE: Record<string, string> = {
  APPROVED: "bg-emerald-500",
  DISPATCHED: "bg-sky-500",
  ACKNOWLEDGED: "bg-violet-500",
  IN_TRANSIT: "bg-blue-500 animate-pulse",
  NEEDS_APPROVAL: "bg-amber-500 animate-pulse",
  REJECTED: "bg-rose-500",
  FAILED: "bg-red-500",
  DRAFT: "bg-slate-500",
  COMPLETED: "bg-emerald-400",
  REPLAN_REQUIRED: "bg-orange-500 animate-pulse",
};

// -------------------------------------------------------------------------
// Main client component
// -------------------------------------------------------------------------

interface DashboardClientProps {
  planId: string;
}

export default function DashboardClient({ planId }: DashboardClientProps) {
  const [plan, setPlan] = useState<DeliveryPlan | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const handleApiError = useApiErrorToast();

  const loadPlan = useCallback(
    async (silent = false) => {
      if (!silent) setIsLoading(true);
      setIsRefreshing(true);
      try {
        const fetched = await getPlan(planId);
        setPlan(fetched);
        setFetchError(null);
      } catch (err: unknown) {
        const e = err as ApiError;
        setFetchError(e?.message ?? "Failed to load plan");
        handleApiError(err, "Failed to load plan");
      } finally {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    },
    [planId, handleApiError]
  );

  useEffect(() => {
    loadPlan();
  }, [loadPlan]);

  // Poll plan status every 10s to pick up agent state changes
  useEffect(() => {
    const interval = setInterval(() => loadPlan(true), 10_000);
    return () => clearInterval(interval);
  }, [loadPlan]);

  const handlePlanUpdate = useCallback((updated: DeliveryPlan) => {
    setPlan(updated);
  }, []);

  const handleDispatchResult = useCallback(
    (_result: DispatchResult) => {
      // Re-fetch plan to get updated status after dispatch
      setTimeout(() => loadPlan(true), 1500);
    },
    [loadPlan]
  );

  // -----------------------------------------------------------------------
  // Render states
  // -----------------------------------------------------------------------

  if (isLoading) return <LoadingSkeleton />;

  if (fetchError && !plan) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-slate-950 gap-4 text-center px-6">
        <div className="flex items-center justify-center h-20 w-20 rounded-full bg-rose-950/60 border border-rose-800/60">
          <AlertTriangle className="h-10 w-10 text-rose-400" />
        </div>
        <h1 className="text-2xl font-bold text-slate-100">Plan not found</h1>
        <p className="text-slate-400 max-w-md text-sm">{fetchError}</p>
        <p className="text-xs text-slate-600 font-mono">{planId}</p>
        <button
          id="retry-load-btn"
          onClick={() => loadPlan()}
          className="mt-2 flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 
                     text-sm font-medium rounded-xl px-5 py-2.5 transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Retry
        </button>
      </div>
    );
  }

  if (!plan) return null;

  const pulseDot = STATUS_PULSE[plan.status] ?? "bg-slate-500";

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-100 overflow-hidden">
      {/* ----------------------------------------------------------------- */}
      {/* Topbar                                                            */}
      {/* ----------------------------------------------------------------- */}
      <header
        id="dashboard-header"
        className="flex items-center justify-between px-5 py-3 
                   border-b border-slate-800/60 bg-slate-900/80 backdrop-blur-md shrink-0"
      >
        <div className="flex items-center gap-3 min-w-0">
          {/* Logo / brand */}
          <div className="flex items-center gap-2 shrink-0">
            <div className="flex items-center justify-center h-8 w-8 rounded-lg bg-indigo-600/20 border border-indigo-500/30">
              <Radio className="h-4 w-4 text-indigo-400" />
            </div>
            <div className="hidden sm:block">
              <p className="text-sm font-bold text-slate-100 leading-none">
                ReliefRoute
              </p>
              <p className="text-[10px] text-slate-500 leading-none mt-0.5">
                Operator Dashboard
              </p>
            </div>
          </div>

          <div className="h-4 w-px bg-slate-800 shrink-0" />

          {/* Plan ID + Status */}
          <div className="flex items-center gap-2 min-w-0">
            <div className={`h-2 w-2 rounded-full shrink-0 ${pulseDot}`} />
            <p className="text-xs font-mono text-slate-400 truncate max-w-[200px] sm:max-w-[320px]">
              {plan.plan_id}
            </p>
            <span className="shrink-0 text-xs font-bold text-slate-300 bg-slate-800/80 border border-slate-700/50 px-2.5 py-1 rounded-full">
              {plan.status}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {/* Live indicator */}
          <div className="flex items-center gap-1.5 text-xs text-emerald-400/80">
            <Activity className="h-3.5 w-3.5" />
            <span className="font-medium hidden md:inline">Live</span>
          </div>

          {/* Refresh */}
          <button
            id="refresh-plan-btn"
            onClick={() => loadPlan()}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 
                       bg-slate-800/60 hover:bg-slate-800 border border-slate-700/50 
                       rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
      </header>

      {/* ----------------------------------------------------------------- */}
      {/* Main body                                                         */}
      {/* ----------------------------------------------------------------- */}
      <main className="flex-1 grid grid-rows-[1fr_auto] lg:grid-rows-1 lg:grid-cols-[1fr_360px] gap-3 p-3 overflow-hidden min-h-0">
        {/* ---- Left column: Map + Dispatch ---- */}
        <div className="flex flex-col gap-3 min-h-0 overflow-hidden">
          {/* Map — takes most vertical space */}
          <div
            id="map-container"
            className="flex-1 min-h-[280px] rounded-2xl overflow-hidden"
          >
            <MapView plan={plan} />
          </div>

          {/* Dispatch Panel — below map */}
          <div className="shrink-0">
            <DispatchPanel plan={plan} onDispatchResult={handleDispatchResult} />
          </div>
        </div>

        {/* ---- Right column: Approval + Audit ---- */}
        <div className="flex flex-col gap-3 min-h-0 overflow-hidden">
          {/* Approval Panel */}
          <div className="shrink-0">
            <ApprovalPanel plan={plan} onPlanUpdate={handlePlanUpdate} />
          </div>

          {/* Audit Trail — fills remaining height */}
          <div className="flex-1 min-h-[200px] overflow-hidden">
            <AuditTrail planId={planId} />
          </div>
        </div>
      </main>
    </div>
  );
}
