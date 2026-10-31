"use client";
// app/components/Toast.tsx
// Global toast notification system. Surfaces API errors prominently.
// 502/503/504 degrade toasts get a red "SYSTEM DEGRADED" banner.

import React, {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from "react";
import { X, AlertTriangle, CheckCircle, Info, WifiOff } from "lucide-react";

// -------------------------------------------------------------------------
// Types
// -------------------------------------------------------------------------

export type ToastVariant = "success" | "error" | "info" | "degraded";

export interface ToastMessage {
  id: string;
  variant: ToastVariant;
  title: string;
  body?: string;
  duration?: number; // ms, 0 = sticky
}

// -------------------------------------------------------------------------
// Context
// -------------------------------------------------------------------------

interface ToastContextValue {
  addToast: (msg: Omit<ToastMessage, "id">) => void;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}

// -------------------------------------------------------------------------
// Individual toast
// -------------------------------------------------------------------------

const VARIANT_STYLES: Record<ToastVariant, string> = {
  success: "border-emerald-500/50 bg-emerald-950/90 text-emerald-100",
  error: "border-rose-500/60 bg-rose-950/95 text-rose-100",
  info: "border-sky-500/50 bg-sky-950/90 text-sky-100",
  degraded:
    "border-red-500 bg-red-950/95 text-red-100 ring-1 ring-red-500/40",
};

const VARIANT_ICONS: Record<ToastVariant, React.ReactNode> = {
  success: <CheckCircle className="h-5 w-5 text-emerald-400 shrink-0" />,
  error: <AlertTriangle className="h-5 w-5 text-rose-400 shrink-0" />,
  info: <Info className="h-5 w-5 text-sky-400 shrink-0" />,
  degraded: <WifiOff className="h-5 w-5 text-red-400 shrink-0" />,
};

function ToastItem({
  toast,
  onRemove,
}: {
  toast: ToastMessage;
  onRemove: (id: string) => void;
}) {
  return (
    <div
      id={`toast-${toast.id}`}
      role="alert"
      aria-live="assertive"
      className={`
        flex items-start gap-3 w-full max-w-sm rounded-xl border px-4 py-3
        shadow-2xl backdrop-blur-md pointer-events-auto
        animate-in slide-in-from-right-5 fade-in duration-300
        ${VARIANT_STYLES[toast.variant]}
      `}
    >
      {VARIANT_ICONS[toast.variant]}
      <div className="flex-1 min-w-0">
        {toast.variant === "degraded" && (
          <p className="text-xs font-bold uppercase tracking-widest text-red-300 mb-0.5">
            ⚠ System Degraded
          </p>
        )}
        <p className="text-sm font-semibold leading-snug">{toast.title}</p>
        {toast.body && (
          <p className="text-xs opacity-80 mt-0.5 leading-relaxed break-words">
            {toast.body}
          </p>
        )}
      </div>
      <button
        id={`toast-dismiss-${toast.id}`}
        onClick={() => onRemove(toast.id)}
        className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
        aria-label="Dismiss notification"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

// -------------------------------------------------------------------------
// Provider
// -------------------------------------------------------------------------

let _counter = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const addToast = useCallback(
    (msg: Omit<ToastMessage, "id">) => {
      const id = `toast-${++_counter}`;
      const duration = msg.duration ?? (msg.variant === "degraded" ? 0 : 5000);
      setToasts((prev) => [...prev.slice(-4), { ...msg, id, duration }]);
      if (duration > 0) {
        const timer = setTimeout(() => removeToast(id), duration);
        timers.current.set(id, timer);
      }
    },
    [removeToast]
  );

  return (
    <ToastContext.Provider value={{ addToast, removeToast }}>
      {children}
      {/* Toast portal */}
      <div
        aria-label="Notifications"
        className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 pointer-events-none"
      >
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onRemove={removeToast} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// -------------------------------------------------------------------------
// Convenience hook to surface API errors
// -------------------------------------------------------------------------

import type { ApiError } from "@/app/lib/api";

export function useApiErrorToast() {
  const { addToast } = useToast();

  return useCallback(
    (err: unknown, fallbackTitle = "Request failed") => {
      const e = err as ApiError;
      if (e?.isConflict) {
        addToast({
          variant: "info",
          title: "Action already in progress",
          body:
            "This action has already been performed. No duplicate will be sent.",
        });
        return;
      }
      if (e?.isDegraded) {
        addToast({
          variant: "degraded",
          title: e.message ?? fallbackTitle,
          body: `Provider: ${e.code}. The system is operating in degraded mode.`,
          duration: 0, // sticky until dismissed
        });
        return;
      }
      addToast({
        variant: "error",
        title: fallbackTitle,
        body: e?.message ?? String(err),
      });
    },
    [addToast]
  );
}
