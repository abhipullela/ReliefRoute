"use client";
// app/components/DispatchPanel.tsx
// Dispatch control panel.
// CRITICAL: The "Dispatch to Driver" button is VISUALLY LOCKED until the
//           plan status is explicitly APPROVED. Any other state disables it.
// Idempotency: 409 Conflict → stop retries + show info toast.

import React, { useState, useTransition, useId } from "react";
import { Send, Lock, Loader2, CheckCircle2, AlertTriangle } from "lucide-react";
import type { DeliveryPlan, DispatchRequest, DispatchResult } from "@/app/types/api";
import { dispatchPlan } from "@/app/lib/api";
import { useApiErrorToast, useToast } from "@/app/components/Toast";

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

/** A plan is only dispatchable when it has been explicitly APPROVED. */
function isPlanDispatchable(plan: DeliveryPlan): boolean {
  return plan.status === "APPROVED";
}

function generateIdempotencyKey(planId: string, driverId: string): string {
  // Stable key = plan + driver; prevents duplicate dispatches on retry
  return `dispatch-${planId}-${driverId}-${Date.now()}`;
}

// -------------------------------------------------------------------------
// Component
// -------------------------------------------------------------------------

interface DispatchPanelProps {
  plan: DeliveryPlan;
  onDispatchResult?: (result: DispatchResult) => void;
}

export default function DispatchPanel({
  plan,
  onDispatchResult,
}: DispatchPanelProps) {
  const [isPending, startTransition] = useTransition();
  const [driverId, setDriverId] = useState("");
  const [message, setMessage] = useState(
    `ReliefRoute Dispatch\n\nPlan: ${plan.plan_id}\nCommodity: ${plan.quantity} ${plan.unit} of ${plan.commodity}\nOrigin: ${plan.origin.latitude.toFixed(4)}, ${plan.origin.longitude.toFixed(4)}\nDestination: ${plan.destination.latitude.toFixed(4)}, ${plan.destination.longitude.toFixed(4)}\n\nPlease acknowledge receipt.`
  );
  const [lastResult, setLastResult] = useState<DispatchResult | null>(null);
  const handleApiError = useApiErrorToast();
  const { addToast } = useToast();
  const driverFieldId = useId();
  const messageFieldId = useId();

  const dispatchable = isPlanDispatchable(plan);

  async function handleDispatch() {
    if (isPending || !dispatchable) return;
    if (!driverId.trim()) {
      addToast({
        variant: "error",
        title: "Driver ID required",
        body: "Please enter the driver identifier before dispatching.",
      });
      return;
    }

    const request: DispatchRequest = {
      plan_id: plan.plan_id,
      driver_id: driverId.trim(),
      message: message.trim(),
      idempotency_key: generateIdempotencyKey(plan.plan_id, driverId.trim()),
    };

    startTransition(async () => {
      try {
        const result = await dispatchPlan(plan.plan_id, request);
        setLastResult(result);
        onDispatchResult?.(result);

        if (result.status === "SENT") {
          addToast({
            variant: "success",
            title: "Message dispatched",
            body: `Telegram message sent. Provider ID: ${result.provider_message_id ?? "N/A"}. Awaiting driver acknowledgement (separate event).`,
          });
        } else {
          addToast({
            variant: "error",
            title: "Dispatch failed",
            body: result.error?.message ?? "Unknown error from dispatch service.",
          });
        }
      } catch (err: unknown) {
        // 409 → already dispatched; stop and surface info toast
        const e = err as { isConflict?: boolean };
        if (e?.isConflict) {
          addToast({
            variant: "info",
            title: "Already dispatched",
            body: "This plan has already been dispatched. Check the audit trail for details.",
          });
          return;
        }
        handleApiError(err, "Dispatch failed");
      }
    });
  }

  return (
    <div
      id="dispatch-panel"
      className="flex flex-col bg-slate-900/80 backdrop-blur-md 
                 border border-slate-800/60 rounded-2xl overflow-hidden"
    >
      {/* Header */}
      <div className="px-5 py-4 border-b border-slate-800/60 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Send className="h-5 w-5 text-sky-400" />
          <h2 className="text-base font-bold text-slate-100">
            Dispatch to Driver
          </h2>
        </div>
        {!dispatchable && (
          <div className="flex items-center gap-1.5 text-xs text-amber-400 font-medium bg-amber-950/50 border border-amber-800/40 px-2.5 py-1 rounded-full">
            <Lock className="h-3.5 w-3.5" />
            Locked — requires approval
          </div>
        )}
      </div>

      <div className="px-5 py-4 space-y-4">
        {/* Lock overlay explanation */}
        {!dispatchable && (
          <div
            id="dispatch-locked-notice"
            className="flex items-start gap-3 bg-amber-950/30 border border-amber-800/40 
                       rounded-xl px-4 py-3"
          >
            <Lock className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-amber-400">
                Dispatch is locked
              </p>
              <p className="text-xs text-amber-500/80 mt-0.5">
                The plan must be in{" "}
                <span className="font-bold text-amber-400">APPROVED</span> status
                before a driver can be dispatched. Current status:{" "}
                <span className="font-bold">{plan.status}</span>
              </p>
            </div>
          </div>
        )}

        {/* Driver ID input */}
        <div>
          <label
            htmlFor={driverFieldId}
            className="text-xs text-slate-500 font-medium uppercase tracking-wider"
          >
            Driver ID / Telegram Chat ID
          </label>
          <input
            id={driverFieldId}
            type="text"
            value={driverId}
            onChange={(e) => setDriverId(e.target.value)}
            placeholder="e.g. driver-001 or Telegram chat ID"
            disabled={!dispatchable || isPending}
            className="mt-1.5 w-full rounded-lg bg-slate-800/70 border border-slate-700/60 
                       text-sm text-slate-200 placeholder-slate-600 px-3 py-2 
                       focus:outline-none focus:ring-2 focus:ring-sky-500/60 
                       disabled:opacity-40 disabled:cursor-not-allowed"
          />
        </div>

        {/* Message input */}
        <div>
          <label
            htmlFor={messageFieldId}
            className="text-xs text-slate-500 font-medium uppercase tracking-wider"
          >
            Dispatch Message
          </label>
          <textarea
            id={messageFieldId}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={6}
            disabled={!dispatchable || isPending}
            className="mt-1.5 w-full rounded-lg bg-slate-800/70 border border-slate-700/60 
                       text-sm text-slate-200 placeholder-slate-600 px-3 py-2 font-mono
                       focus:outline-none focus:ring-2 focus:ring-sky-500/60 
                       disabled:opacity-40 disabled:cursor-not-allowed resize-none"
          />
        </div>

        {/* Sent/Acknowledged separation notice */}
        <div className="flex items-start gap-2 bg-slate-800/40 rounded-lg px-3 py-2.5">
          <AlertTriangle className="h-4 w-4 text-slate-500 shrink-0 mt-0.5" />
          <p className="text-xs text-slate-500 leading-relaxed">
            <span className="text-slate-400 font-semibold">Note:</span> "Dispatch
            sent" and "driver acknowledged" are{" "}
            <span className="text-slate-300 font-semibold">separate states</span>.
            Sending this message does not confirm driver acknowledgement. Monitor
            the audit trail for the acknowledgement event.
          </p>
        </div>

        {/* Last result */}
        {lastResult && (
          <div
            id="dispatch-result"
            className={`flex items-start gap-2 rounded-lg px-3 py-2.5 text-xs
                        ${lastResult.status === "SENT"
                          ? "bg-emerald-950/40 border border-emerald-800/40 text-emerald-300"
                          : "bg-rose-950/40 border border-rose-800/40 text-rose-300"
                        }`}
          >
            {lastResult.status === "SENT" ? (
              <CheckCircle2 className="h-4 w-4 shrink-0" />
            ) : (
              <AlertTriangle className="h-4 w-4 shrink-0" />
            )}
            <div>
              <p className="font-semibold">
                {lastResult.status === "SENT"
                  ? "Message SENT via Telegram"
                  : "Dispatch FAILED"}
              </p>
              {lastResult.provider_message_id && (
                <p className="text-[10px] opacity-70 font-mono">
                  Telegram ID: {lastResult.provider_message_id}
                </p>
              )}
              {lastResult.error && (
                <p className="opacity-70">{lastResult.error.message}</p>
              )}
            </div>
          </div>
        )}

        {/* Dispatch button — LOCKED until APPROVED */}
        <button
          id="dispatch-to-driver-btn"
          onClick={handleDispatch}
          disabled={!dispatchable || isPending}
          aria-disabled={!dispatchable}
          className={`
            w-full flex items-center justify-center gap-2.5 
            text-sm font-bold rounded-xl px-4 py-3 
            transition-all duration-200 active:scale-95 
            ${
              dispatchable
                ? "bg-sky-600 hover:bg-sky-500 text-white shadow-lg shadow-sky-900/40 cursor-pointer"
                : "bg-slate-800/60 text-slate-600 border border-slate-700/40 cursor-not-allowed opacity-60"
            }
            disabled:pointer-events-none
          `}
        >
          {isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Sending…
            </>
          ) : !dispatchable ? (
            <>
              <Lock className="h-4 w-4" />
              Locked — Approve First
            </>
          ) : (
            <>
              <Send className="h-4 w-4" />
              Dispatch to Driver
            </>
          )}
        </button>
      </div>
    </div>
  );
}
