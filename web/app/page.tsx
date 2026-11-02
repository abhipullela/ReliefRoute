"use client";
// app/page.tsx — ReliefRoute Admin Dashboard Entry / Modern Login

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Shield,
  Eye,
  EyeOff,
  AlertTriangle,
  Loader2,
  Radio,
  ArrowRight,
  Activity,
  Lock,
  Compass,
} from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@reliefroute.gov");
  const [password, setPassword] = useState("••••••••••••");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!email.trim() || !password.trim()) {
      setError("Please enter your administrator credentials.");
      return;
    }

    setLoading(true);
    // Smooth transition into the interactive operations map (Live mode)
    setTimeout(() => {
      router.push("/map?mode=live");
    }, 700);
  }

  function handleDemoLogin() {
    setEmail("operator.emergency@reliefroute.gov");
    setPassword("ReliefRoute2024!");
    setError("");
    setLoading(true);
    // Demo mode with pre-seeded scenario plans
    setTimeout(() => {
      router.push("/map?mode=demo");
    }, 500);
  }

  return (
    <main className="min-h-screen bg-slate-950 flex flex-col items-center justify-center px-4 relative overflow-hidden select-none">
      {/* Dynamic Ambient Background with Glowing Orbs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-32 left-1/2 -translate-x-1/2 h-[650px] w-[650px] rounded-full bg-indigo-600/15 blur-3xl" />
        <div className="absolute -bottom-32 left-1/4 h-[500px] w-[500px] rounded-full bg-sky-600/10 blur-3xl" />
        <div className="absolute top-1/3 -right-20 h-[450px] w-[450px] rounded-full bg-rose-600/10 blur-3xl" />
        {/* Subtle grid pattern */}
        <div
          className="absolute inset-0 opacity-[0.035]"
          style={{
            backgroundImage:
              "linear-gradient(#6366f1 1px, transparent 1px), linear-gradient(90deg, #6366f1 1px, transparent 1px)",
            backgroundSize: "48px 48px",
          }}
        />
      </div>

      <div className="relative z-10 w-full max-w-md">
        {/* Brand Header */}
        <div className="flex flex-col items-center text-center mb-8">
          <div className="relative mb-4">
            <div className="absolute inset-0 rounded-2xl bg-indigo-500/30 blur-xl animate-pulse" />
            <div className="relative flex items-center justify-center h-20 w-20 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-slate-900 border border-indigo-500/40 shadow-2xl shadow-indigo-950">
              <Radio className="h-10 w-10 text-indigo-400" />
            </div>
            <div className="absolute -bottom-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500/20 border border-emerald-400/50">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
            </div>
          </div>

          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 text-xs font-semibold mb-2">
            <Activity className="h-3 w-3 text-indigo-400 animate-pulse" />
            Autonomous Emergency Logistics System
          </div>

          <h1 className="text-3xl sm:text-4xl font-black text-slate-100 tracking-tight">
            ReliefRoute
          </h1>
          <p className="text-slate-400 text-sm mt-1 max-w-xs">
            Admin Command Console & Active Flood Dispatch Portal
          </p>
        </div>

        {/* Login Card */}
        <div className="bg-slate-900/80 backdrop-blur-xl border border-slate-800/80 rounded-2xl p-7 sm:p-8 shadow-2xl shadow-black/60">
          <div className="flex items-center justify-between pb-5 mb-5 border-b border-slate-800/70">
            <div className="flex items-center gap-2.5">
              <div className="flex items-center justify-center h-9 w-9 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400">
                <Shield className="h-4 w-4" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-slate-100">
                  Admin Sign In
                </h2>
                <p className="text-[11px] text-slate-400">
                  Authorized operators only
                </p>
              </div>
            </div>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-md bg-slate-800 border border-slate-700/60 text-slate-300">
              Level 4 Clearance
            </span>
          </div>

          {error && (
            <div className="mb-4 flex items-center gap-2 text-xs text-rose-300 bg-rose-950/40 border border-rose-800/50 rounded-xl px-3.5 py-2.5">
              <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="admin-email"
                className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5"
              >
                Operator Email
              </label>
              <div className="relative">
                <input
                  id="admin-email"
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setError("");
                  }}
                  placeholder="admin@reliefroute.gov"
                  className="w-full rounded-xl bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-200 placeholder-slate-600 px-4 py-2.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500/30 transition-all"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label
                  htmlFor="admin-password"
                  className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider"
                >
                  Password
                </label>
                <span className="text-[11px] text-indigo-400 hover:text-indigo-300 cursor-pointer">
                  Encrypted SSL
                </span>
              </div>
              <div className="relative">
                <input
                  id="admin-password"
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setError("");
                  }}
                  placeholder="••••••••••••"
                  className="w-full rounded-xl bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-200 placeholder-slate-600 px-4 py-2.5 text-sm pr-10 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 transition-all font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 transition-colors p-1"
                  aria-label={showPw ? "Hide password" : "Show password"}
                >
                  {showPw ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            <button
              id="login-submit-btn"
              type="submit"
              disabled={loading}
              className="w-full mt-2 flex items-center justify-center gap-2 bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold rounded-xl px-4 py-3 text-sm transition-all duration-200 active:scale-[0.98] shadow-lg shadow-indigo-900/30 cursor-pointer"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Entering Command Map…
                </>
              ) : (
                <>
                  <Compass className="h-4 w-4" />
                  Launch Flood Operations Map
                  <ArrowRight className="h-4 w-4 ml-1" />
                </>
              )}
            </button>
          </form>

          {/* Quick Demo Access */}
          <div className="mt-5 pt-4 border-t border-slate-800/60 flex flex-col gap-2">
            <button
              type="button"
              onClick={handleDemoLogin}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-slate-800/70 hover:bg-slate-800 border border-slate-700/60 text-slate-300 hover:text-white rounded-xl px-3 py-2 text-xs font-medium transition-colors cursor-pointer"
            >
              <Lock className="h-3.5 w-3.5 text-emerald-400" />
              One-Click Operator Demo Login
            </button>
          </div>
        </div>

        {/* Footer Info */}
        <div className="mt-6 flex flex-col items-center gap-2 text-center text-xs text-slate-500">
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <span>Operational Area: Bengaluru South · Anekal Basin</span>
          </div>
          <p className="text-[11px] text-slate-600">
            ReliefRoute Autonomous Logistics v2.0 · Emergency Operations Console
          </p>
        </div>
      </div>
    </main>
  );
}
