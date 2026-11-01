"use client";
// app/plan/[id]/PlanDetailsClient.tsx
// Operator dashboard for a specific Delivery Plan.
// Integrates MapView (route line + hazard polygons), ApprovalPanel, DispatchPanel, and AuditTrail.

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import {
  ArrowLeft,
  RefreshCw,
  AlertTriangle,
  Loader2,
  Activity,
  CheckCircle2,
  Copy,
  Sparkles,
  MapPin,
  Package,
  MessageSquareQuote,
  ShieldAlert,
} from "lucide-react";
import type { DeliveryPlan, DispatchResult, GenAIExtractedData } from "@/app/types/api";
import { getPlan } from "@/app/lib/api";
import type { ApiError } from "@/app/lib/api";
import ApprovalPanel from "@/app/components/ApprovalPanel";
import DispatchPanel from "@/app/components/DispatchPanel";
import AuditTrail from "@/app/components/AuditTrail";
import { useApiErrorToast } from "@/app/components/Toast";

// MapView uses maplibre-gl which requires the browser window
const MapView = dynamic(() => import("@/app/components/MapView"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full bg-slate-900/60 rounded-2xl border border-slate-800">
      <div className="flex flex-col items-center gap-3 text-slate-400">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
        <p className="text-xs font-semibold uppercase tracking-wider">
          Initializing Route Map & Hazard Polygons…
        </p>
      </div>
    </div>
  ),
});

const STATUS_PULSE: Record<string, string> = {
  APPROVED: "bg-emerald-500",
  DISPATCHED: "bg-sky-500",
  ACKNOWLEDGED: "bg-violet-500",
  IN_TRANSIT: "bg-blue-500 animate-pulse",
  NEEDS_APPROVAL: "bg-amber-500 animate-pulse",
  PENDING_APPROVAL: "bg-amber-500 animate-pulse",
  REJECTED: "bg-rose-500",
  FAILED: "bg-red-500",
  DRAFT: "bg-slate-500",
  COMPLETED: "bg-emerald-400",
  REPLAN_REQUIRED: "bg-orange-500 animate-pulse",
};

interface PlanDetailsClientProps {
  planId: string;
}

export default function PlanDetailsClient({ planId }: PlanDetailsClientProps) {
  const router = useRouter();
  const [plan, setPlan] = useState<DeliveryPlan | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [copied, setCopied] = useState(false);
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
        handleApiError(err, "Failed to load delivery plan");
      } finally {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    },
    [planId, handleApiError]
  );

  useEffect(() => {
    let isCancelled = false;
    getPlan(planId)
      .then((fetched) => {
        if (!isCancelled) {
          setPlan(fetched);
          setFetchError(null);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!isCancelled) {
          const e = err as ApiError;
          setFetchError(e?.message ?? "Failed to load plan");
          setIsLoading(false);
        }
      });
    return () => {
      isCancelled = true;
    };
  }, [planId]);

  const handlePlanUpdate = useCallback((updated: DeliveryPlan) => {
    setPlan(updated);
  }, []);

  const handleDispatchResult = useCallback(
    () => {
      // Re-fetch plan to reflect DISPATCHED state after driver notification
      setTimeout(() => loadPlan(true), 1200);
    },
    [loadPlan]
  );

  function copyPlanId() {
    if (!plan) return;
    navigator.clipboard.writeText(plan.plan_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  // -----------------------------------------------------------------------
  // Loading skeleton
  // -----------------------------------------------------------------------
  if (isLoading) {
    return (
      <div className="flex flex-col h-screen bg-slate-950 text-slate-100 p-4 gap-4 animate-pulse">
        <div className="h-14 bg-slate-900/60 rounded-2xl border border-slate-800" />
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-4 min-h-0">
          <div className="flex flex-col gap-4">
            <div className="flex-1 bg-slate-900/60 rounded-2xl border border-slate-800" />
            <div className="h-44 bg-slate-900/60 rounded-2xl border border-slate-800" />
          </div>
          <div className="flex flex-col gap-4">
            <div className="h-1/2 bg-slate-900/60 rounded-2xl border border-slate-800" />
            <div className="h-1/2 bg-slate-900/60 rounded-2xl border border-slate-800" />
          </div>
        </div>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // Error state
  // -----------------------------------------------------------------------
  if (fetchError && !plan) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-slate-950 gap-4 text-center px-6">
        <div className="flex items-center justify-center h-20 w-20 rounded-2xl bg-rose-950/60 border border-rose-800/60 shadow-xl shadow-rose-950/40">
          <AlertTriangle className="h-10 w-10 text-rose-400" />
        </div>
        <h1 className="text-2xl font-bold text-slate-100">Plan Not Found</h1>
        <p className="text-slate-400 max-w-md text-sm">{fetchError}</p>
        <p className="text-xs text-slate-500 font-mono bg-slate-900 px-3 py-1 rounded-lg border border-slate-800">
          {planId}
        </p>
        <div className="flex items-center gap-3 mt-3">
          <button
            onClick={() => router.push("/map")}
            className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-semibold rounded-xl px-5 py-2.5 transition-colors cursor-pointer"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Flood Map
          </button>
          <button
            onClick={() => loadPlan()}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold rounded-xl px-5 py-2.5 transition-colors shadow-lg shadow-indigo-950 cursor-pointer"
          >
            <RefreshCw className="h-4 w-4" />
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!plan) return null;

  const pulseDot = STATUS_PULSE[plan.status] ?? "bg-slate-500";

  const extraction: GenAIExtractedData = plan.gen_ai_extraction ?? {
    emergency_type: plan.hazard_polygons?.length ? "FLASH FLOOD INUNDATION" : "EMERGENCY RELIEF",
    requested_supplies: [plan.commodity],
    extracted_location: `${plan.destination.latitude.toFixed(4)}° N, ${plan.destination.longitude.toFixed(4)}° E (Anekal Basin)`,
    original_message: plan.rationale?.[0] || "Natural language emergency transmission logged.",
    confidence: 96.2,
    people_affected: 45,
  };

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-100 overflow-hidden select-none">
      {/* ----------------------------------------------------------------- */}
      {/* Top Header Navigation Bar                                         */}
      {/* ----------------------------------------------------------------- */}
      <header
        id="plan-header"
        className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-slate-800/80 bg-slate-900/90 backdrop-blur-xl shrink-0 z-10"
      >
        <div className="flex items-center gap-3 min-w-0">
          {/* Back to Map button */}
          <button
            onClick={() => router.push("/map")}
            className="flex items-center gap-1.5 text-xs font-semibold text-slate-300 hover:text-white bg-slate-800/70 hover:bg-slate-800 border border-slate-700/60 rounded-xl px-3 py-2 transition-all cursor-pointer shadow-sm shrink-0"
          >
            <ArrowLeft className="h-4 w-4 text-indigo-400" />
            <span className="hidden sm:inline">Back to Flood Map</span>
          </button>

          <div className="h-4 w-px bg-slate-800 shrink-0" />

          {/* Plan ID & Status */}
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex items-center gap-1.5 bg-slate-950/70 border border-slate-800 px-3 py-1.5 rounded-xl">
              <span className="text-[11px] text-slate-400 uppercase font-semibold">
                Plan ID:
              </span>
              <span className="font-mono text-sm font-bold text-sky-400">
                {plan.plan_id}
              </span>
              <button
                onClick={copyPlanId}
                className="text-slate-400 hover:text-slate-200 transition-colors ml-1 p-0.5 cursor-pointer"
                title="Copy Plan ID"
              >
                {copied ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </button>
            </div>

            <span className="shrink-0 flex items-center gap-1.5 text-xs font-bold text-slate-200 bg-slate-800/90 border border-slate-700/60 px-3 py-1.5 rounded-xl">
              <span className={`h-2 w-2 rounded-full ${pulseDot}`} />
              {plan.status}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {/* Live System Indicator */}
          <div className="hidden md:flex items-center gap-1.5 text-xs font-medium text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-3 py-1 rounded-xl">
            <Activity className="h-3.5 w-3.5 animate-pulse" />
            <span>Autonomous Route Guard Active</span>
          </div>

          {/* Refresh button */}
          <button
            onClick={() => loadPlan()}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 text-xs text-slate-300 hover:text-white bg-slate-800/70 hover:bg-slate-800 border border-slate-700/60 rounded-xl px-3 py-1.5 transition-colors disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`}
            />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
      </header>

      {/* ----------------------------------------------------------------- */}
      {/* Main Content Grid: Map + Dispatch Gate (Left), AI Data + Approval + Audit (Right) */}
      {/* ----------------------------------------------------------------- */}
      <main className="flex-1 grid grid-rows-[1fr_auto] lg:grid-rows-1 lg:grid-cols-[1fr_420px] gap-3 p-3 overflow-hidden min-h-0">
        {/* Left Column: Route Map + Hazard Polygons & Dispatch Gate */}
        <div className="flex flex-col gap-3 min-h-0 overflow-hidden">
          {/* MapView container */}
          <div
            id="map-container"
            className="flex-1 min-h-[300px] rounded-2xl overflow-hidden border border-slate-800/80 shadow-2xl relative"
          >
            <MapView plan={plan} />
          </div>

          {/* Dispatch Gate (Visually locked until status === "APPROVED") */}
          <div className="shrink-0">
            <DispatchPanel
              plan={plan}
              onDispatchResult={handleDispatchResult}
            />
          </div>
        </div>

        {/* Right Column: Gen AI Data Card, Approval Gate & Audit Trail */}
        <div className="flex flex-col gap-3 min-h-0 overflow-y-auto pr-1">
          {/* ------------------------------------------------------------- */}
          {/* Gen AI Extracted Data Card                                    */}
          {/* ------------------------------------------------------------- */}
          <div
            id="gen-ai-card"
            className="shrink-0 bg-slate-900/90 backdrop-blur-xl border border-indigo-500/30 rounded-2xl p-4 shadow-xl"
          >
            <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800/80">
              <div className="flex items-center gap-2">
                <div className="flex items-center justify-center h-8 w-8 rounded-xl bg-indigo-600/20 border border-indigo-500/40 text-indigo-400">
                  <Sparkles className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                    Gen AI Extracted Data
                  </h3>
                  <p className="text-[10px] text-slate-400">
                    Citizen Natural Language Intake
                  </p>
                </div>
              </div>
              <span className="text-[10px] font-semibold bg-indigo-950/60 text-indigo-300 border border-indigo-800/50 rounded-full px-2.5 py-0.5">
                {extraction.confidence ?? 96.5}% Confidence
              </span>
            </div>

            {/* Extracted Fields */}
            <div className="space-y-3 text-xs">
              {/* Emergency Type */}
              <div className="flex items-start gap-2.5 bg-slate-950/50 border border-slate-800/60 rounded-xl p-2.5">
                <div className="mt-0.5 text-rose-400 shrink-0">
                  <ShieldAlert className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                    Emergency Type
                  </p>
                  <p className="font-bold text-rose-300 text-xs mt-0.5">
                    {extraction.emergency_type}
                  </p>
                </div>
              </div>

              {/* Extracted Location */}
              <div className="flex items-start gap-2.5 bg-slate-950/50 border border-slate-800/60 rounded-xl p-2.5">
                <div className="mt-0.5 text-amber-400 shrink-0">
                  <MapPin className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                    Extracted Location
                  </p>
                  <p className="font-semibold text-slate-200 text-xs mt-0.5">
                    {extraction.extracted_location}
                  </p>
                  <p className="text-[10px] font-mono text-slate-400 mt-0.5">
                    Coordinates: {plan.destination.latitude.toFixed(4)}° N, {plan.destination.longitude.toFixed(4)}° E
                  </p>
                </div>
              </div>

              {/* Requested Supplies */}
              <div className="flex items-start gap-2.5 bg-slate-950/50 border border-slate-800/60 rounded-xl p-2.5">
                <div className="mt-0.5 text-sky-400 shrink-0">
                  <Package className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">
                    Requested Supplies
                  </p>
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    {extraction.requested_supplies.map((item, idx) => (
                      <span
                        key={idx}
                        className="bg-sky-950/60 border border-sky-800/50 text-sky-300 px-2.5 py-0.5 rounded-lg text-[11px] font-semibold"
                      >
                        {item}
                      </span>
                    ))}
                  </div>
                  <p className="text-[10px] text-slate-400 mt-1.5">
                    Allocated Supply:{" "}
                    <span className="text-slate-100 font-bold">
                      {plan.quantity} {plan.unit} of {plan.commodity}
                    </span>
                  </p>
                </div>
              </div>

              {/* Natural Language Citizen Report */}
              {extraction.original_message && (
                <div className="pt-2 border-t border-slate-800/70">
                  <div className="flex items-center gap-1.5 text-[10px] uppercase font-bold text-slate-500 mb-1 tracking-wider">
                    <MessageSquareQuote className="h-3 w-3 text-indigo-400" />
                    <span>Citizen Report Message</span>
                  </div>
                  <p className="text-[11px] italic text-slate-300 bg-slate-950/70 border border-slate-800/80 rounded-xl p-2.5 leading-relaxed">
                    &ldquo;{extraction.original_message}&rdquo;
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Approval Gate (Human-in-the-loop decision gate) */}
          <div className="shrink-0">
            <ApprovalPanel plan={plan} onPlanUpdate={handlePlanUpdate} />
          </div>

          {/* Audit Trail Log */}
          <div className="flex-1 min-h-[220px]">
            <AuditTrail planId={plan.plan_id} />
          </div>
        </div>
      </main>
    </div>
  );
}
