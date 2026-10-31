"use client";
// app/components/ApprovalPanel.tsx
// Sleek side-panel showing plan details + Approve/Reject controls.
// After approval, the DISPATCHED state unlocks the Dispatch button.
// 409 Conflict → "already decided" info toast (no retry).

import React, { useState, useTransition, useId } from "react";
import {
  CheckCircle2,
  XCircle,
  Package,
  MapPin,
  Clock,
  Hash,
  Loader2,
  AlertTriangle,
  ShieldCheck,
} from "lucide-react";
import type { DeliveryPlan, ApprovalRequest } from "@/app/types/api";
import { approvePlan } from "@/app/lib/api";
import { useApiErrorToast } from "@/app/components/Toast";

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

const STATUS_CONFIG: Record<
  string,
  { label: string; color: string; bg: string }
> = {
  DRAFT: { label: "Draft", color: "text-slate-400", bg: "bg-slate-700/50" },
  NEEDS_APPROVAL: {
    label: "Needs Approval",
    color: "text-amber-400",
    bg: "bg-amber-900/40",
  },
  PENDING_APPROVAL: {
    label: "Pending Approval",
    color: "text-amber-400",
    bg: "bg-amber-900/40",
  },
  APPROVED: {
    label: "Approved",
    color: "text-emerald-400",
    bg: "bg-emerald-900/40",
  },
  REJECTED: { label: "Rejected", color: "text-rose-400", bg: "bg-rose-900/40" },
  DISPATCHED: {
    label: "Dispatched",
    color: "text-sky-400",
    bg: "bg-sky-900/40",
  },
  ACKNOWLEDGED: {
    label: "Acknowledged",
    color: "text-violet-400",
    bg: "bg-violet-900/40",
  },
  IN_TRANSIT: {
    label: "In Transit",
    color: "text-blue-400",
    bg: "bg-blue-900/40",
  },
  COMPLETED: {
    label: "Completed",
    color: "text-emerald-400",
    bg: "bg-emerald-900/40",
  },
  FAILED: { label: "Failed", color: "text-red-400", bg: "bg-red-900/40" },
  REPLAN_REQUIRED: {
    label: "Replan Required",
    color: "text-orange-400",
    bg: "bg-orange-900/40",
  },
};

function DetailRow({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-slate-800/60 last:border-0">
      <span className="text-slate-500 mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs text-slate-500 uppercase tracking-wider font-medium">
          {label}
        </p>
        <p className="text-sm text-slate-200 font-medium mt-0.5 break-words">
          {value}
        </p>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------------
// Main component
// -------------------------------------------------------------------------

interface ApprovalPanelProps {
  plan: DeliveryPlan;
  onPlanUpdate: (updated: DeliveryPlan) => void;
}

export default function ApprovalPanel({
  plan,
  onPlanUpdate,
}: ApprovalPanelProps) {
  const [isPending, startTransition] = useTransition();
  const [comment, setComment] = useState("");
  const [justDecided, setJustDecided] = useState<"approved" | "rejected" | null>(null);
  const handleApiError = useApiErrorToast();
  const commentId = useId();

  const canDecide =
    plan.status === "NEEDS_APPROVAL" || plan.status === "DRAFT";
  const isApproved = plan.status === "APPROVED" || plan.status === "DISPATCHED" ||
    plan.status === "ACKNOWLEDGED" || plan.status === "IN_TRANSIT" ||
    plan.status === "COMPLETED";
  const isRejected = plan.status === "REJECTED";

  const statusCfg = STATUS_CONFIG[plan.status] ?? {
    label: plan.status,
    color: "text-slate-400",
    bg: "bg-slate-700/50",
  };

  async function handleDecide(approved: boolean) {
    if (isPending) return;

    const request: ApprovalRequest = {
      plan_id: plan.plan_id,
      approved,
      approver_id: "operator-dashboard", // In a real system, inject auth user ID
      comment: comment.trim() || undefined,
      decided_at: new Date().toISOString(),
    };

    startTransition(async () => {
      try {
        const updated = await approvePlan(plan.plan_id, request);
        setJustDecided(approved ? "approved" : "rejected");
        onPlanUpdate(updated);
      } catch (err) {
        handleApiError(
          err,
          approved ? "Approval failed" : "Rejection failed"
        );
      }
    });
  }

  return (
    <div
      id="approval-panel"
      className="flex flex-col h-full bg-slate-900/80 backdrop-blur-md 
                 border border-slate-800/60 rounded-2xl overflow-hidden"
    >
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-800/60 bg-slate-900/60">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-indigo-400" />
            <h2 className="text-base font-bold text-slate-100">
              Approval Gate
            </h2>
          </div>
          <span
            id="plan-status-badge"
            className={`text-xs font-semibold px-2.5 py-1 rounded-full ${statusCfg.bg} ${statusCfg.color} border border-current/20`}
          >
            {statusCfg.label}
          </span>
        </div>
        <p className="text-xs text-slate-500 mt-1 font-mono truncate">
          {plan.plan_id}
        </p>
      </div>

      {/* Scrollable details */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-1">
        <DetailRow
          icon={<Package className="h-4 w-4" />}
          label="Commodity"
          value={`${plan.commodity} — ${plan.quantity} ${plan.unit}`}
        />
        <DetailRow
          icon={<Hash className="h-4 w-4" />}
          label="Supplier"
          value={plan.supplier_id}
        />
        <DetailRow
          icon={<MapPin className="h-4 w-4" />}
          label="Origin"
          value={`${plan.origin.latitude.toFixed(5)}, ${plan.origin.longitude.toFixed(5)}`}
        />
        <DetailRow
          icon={<MapPin className="h-4 w-4" />}
          label="Destination"
          value={`${plan.destination.latitude.toFixed(5)}, ${plan.destination.longitude.toFixed(5)}`}
        />
        {plan.route && (
          <>
            <DetailRow
              icon={<Clock className="h-4 w-4" />}
              label="Estimated Duration"
              value={`${Math.round(plan.route.duration_s / 60)} min`}
            />
            <DetailRow
              icon={<MapPin className="h-4 w-4" />}
              label="Distance"
              value={`${(plan.route.distance_m / 1000).toFixed(1)} km`}
            />
            <DetailRow
              icon={<AlertTriangle className="h-4 w-4" />}
              label="Route Risk Level"
              value={
                <span
                  className={
                    plan.route.risk_level === "HIGH"
                      ? "text-red-400"
                      : plan.route.risk_level === "MODERATE"
                      ? "text-amber-400"
                      : "text-emerald-400"
                  }
                >
                  {plan.route.risk_level}
                </span>
              }
            />
          </>
        )}
        <DetailRow
          icon={<Clock className="h-4 w-4" />}
          label="Created At"
          value={new Date(plan.created_at).toLocaleString()}
        />

        {/* Rationale */}
        {plan.rationale.length > 0 && (
          <div className="pt-3">
            <p className="text-xs text-slate-500 uppercase tracking-wider font-medium mb-2">
              Agent Rationale
            </p>
            <ul className="space-y-1.5">
              {plan.rationale.map((r, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-slate-300">
                  <span className="text-indigo-400 shrink-0 mt-0.5">•</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Route warnings */}
        {plan.route?.warnings && plan.route.warnings.length > 0 && (
          <div className="pt-3">
            <p className="text-xs text-amber-400/80 uppercase tracking-wider font-medium mb-2">
              Route Warnings
            </p>
            <ul className="space-y-1">
              {plan.route.warnings.map((w, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-amber-300/80">
                  <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Action area */}
      <div className="px-5 py-4 border-t border-slate-800/60 space-y-3">
        {isApproved && !justDecided && (
          <div className="flex items-center gap-2 text-emerald-400 text-sm font-semibold">
            <CheckCircle2 className="h-4 w-4" />
            Plan is approved — dispatch is unlocked.
          </div>
        )}

        {isRejected && (
          <div className="flex items-center gap-2 text-rose-400 text-sm font-semibold">
            <XCircle className="h-4 w-4" />
            Plan has been rejected.
          </div>
        )}

        {justDecided === "approved" && (
          <div className="flex items-center gap-2 text-emerald-400 text-sm font-semibold animate-in fade-in">
            <CheckCircle2 className="h-4 w-4" />
            Approved! Dispatch is now unlocked.
          </div>
        )}
        {justDecided === "rejected" && (
          <div className="flex items-center gap-2 text-rose-400 text-sm font-semibold animate-in fade-in">
            <XCircle className="h-4 w-4" />
            Plan rejected.
          </div>
        )}

        {canDecide && (
          <>
            <div>
              <label
                htmlFor={commentId}
                className="text-xs text-slate-500 font-medium uppercase tracking-wider"
              >
                Optional Comment
              </label>
              <textarea
                id={commentId}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Add a note for the audit trail…"
                rows={2}
                className="mt-1.5 w-full rounded-lg bg-slate-800/70 border border-slate-700/60 
                           text-sm text-slate-200 placeholder-slate-600 px-3 py-2 
                           focus:outline-none focus:ring-2 focus:ring-indigo-500/60 resize-none"
              />
            </div>

            <div className="flex gap-3">
              <button
                id="approve-plan-btn"
                onClick={() => handleDecide(true)}
                disabled={isPending}
                className="flex-1 flex items-center justify-center gap-2 
                           bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed
                           text-white text-sm font-semibold rounded-xl px-4 py-2.5 
                           transition-all duration-200 active:scale-95 shadow-lg shadow-emerald-900/30"
              >
                {isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                Approve Plan
              </button>

              <button
                id="reject-plan-btn"
                onClick={() => handleDecide(false)}
                disabled={isPending}
                className="flex-1 flex items-center justify-center gap-2 
                           bg-rose-900/60 hover:bg-rose-800/70 border border-rose-700/50 
                           disabled:opacity-50 disabled:cursor-not-allowed
                           text-rose-300 text-sm font-semibold rounded-xl px-4 py-2.5 
                           transition-all duration-200 active:scale-95"
              >
                {isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <XCircle className="h-4 w-4" />
                )}
                Reject
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
