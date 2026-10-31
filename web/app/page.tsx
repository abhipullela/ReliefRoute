"use client";
// app/page.tsx — Plan ID entry / landing page.
// Redirects to /dashboard/{plan_id}.

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Radio, ArrowRight, AlertTriangle } from "lucide-react";

export default function HomePage() {
  const router = useRouter();
  const [planId, setPlanId] = useState("");
  const [error, setError] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = planId.trim();
    if (!trimmed) {
      setError("Please enter a plan ID.");
      return;
    }
    router.push(`/dashboard/${encodeURIComponent(trimmed)}`);
  }

  return (
    <main className="min-h-screen bg-slate-950 flex flex-col items-center justify-center px-6">
      {/* Gradient background glow */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 h-[600px] w-[600px] 
                        rounded-full bg-indigo-900/20 blur-3xl" />
        <div className="absolute bottom-0 right-0 h-80 w-80 rounded-full bg-sky-900/10 blur-3xl" />
      </div>

      <div className="relative z-10 w-full max-w-md">
        {/* Logo */}
        <div className="flex flex-col items-center mb-10">
          <div className="flex items-center justify-center h-16 w-16 rounded-2xl 
                          bg-indigo-600/20 border border-indigo-500/40 mb-4 shadow-xl shadow-indigo-900/30">
            <Radio className="h-8 w-8 text-indigo-400" />
          </div>
          <h1 className="text-3xl font-black text-slate-100 tracking-tight">
            ReliefRoute
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Autonomous Emergency Logistics · Operator Dashboard
          </p>
        </div>

        {/* Card */}
        <div className="bg-slate-900/80 backdrop-blur-md border border-slate-800/60 
                        rounded-2xl p-8 shadow-2xl">
          <h2 className="text-lg font-bold text-slate-100 mb-1">
            Load Delivery Plan
          </h2>
          <p className="text-sm text-slate-500 mb-6">
            Enter the plan ID to open the operator dashboard for that delivery.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="plan-id-input"
                className="text-xs font-medium text-slate-500 uppercase tracking-wider"
              >
                Plan ID
              </label>
              <input
                id="plan-id-input"
                type="text"
                value={planId}
                onChange={(e) => {
                  setPlanId(e.target.value);
                  setError("");
                }}
                placeholder="e.g. plan-abc123"
                autoFocus
                className="mt-1.5 w-full rounded-xl bg-slate-800/70 border border-slate-700/60 
                           text-slate-200 placeholder-slate-600 px-4 py-2.5 text-sm font-mono
                           focus:outline-none focus:ring-2 focus:ring-indigo-500/60 
                           transition-shadow"
              />
              {error && (
                <p className="text-xs text-rose-400 mt-1.5 flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  {error}
                </p>
              )}
            </div>

            <button
              id="load-plan-btn"
              type="submit"
              className="w-full flex items-center justify-center gap-2 
                         bg-indigo-600 hover:bg-indigo-500 text-white font-semibold 
                         rounded-xl px-4 py-2.5 text-sm transition-all duration-200 
                         active:scale-95 shadow-lg shadow-indigo-900/40"
            >
              Open Dashboard
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>
        </div>

        {/* Warning */}
        <div className="mt-6 flex items-start gap-2 text-xs text-slate-600">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5 text-amber-700" />
          <p>
            Hazard polygons shown on the map represent{" "}
            <span className="text-amber-600/80 font-semibold">
              modeled forecast risk
            </span>{" "}
            only — not verified road closures or guaranteed-safe routes.
          </p>
        </div>
      </div>
    </main>
  );
}
