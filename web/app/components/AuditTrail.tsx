"use client";
// app/components/AuditTrail.tsx
// Live scrolling terminal-style audit event feed.
// Polls GET /api/v1/audit-events?entity_id={plan_id} every 5 seconds.
// Append-only: never re-renders existing events; only appends new ones.
// Surfaces API errors as a degraded banner inside the terminal.

import React, {
  useEffect,
  useRef,
  useState,
  useCallback,
} from "react";
import { Terminal, RefreshCw, AlertTriangle, WifiOff } from "lucide-react";
import type { AuditEvent } from "@/app/types/api";
import { getAuditEvents } from "@/app/lib/api";
import type { ApiError } from "@/app/lib/api";

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

const POLL_INTERVAL_MS = 5000;

const OUTCOME_STYLES: Record<string, string> = {
  SUCCESS: "text-emerald-400",
  FAILURE: "text-rose-400",
  DEGRADED: "text-amber-400",
  SKIPPED: "text-slate-500",
  CONFLICT: "text-violet-400",
};

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "??:??:??";
  }
}

function AuditEventRow({ event, index }: { event: AuditEvent; index: number }) {
  const outcomeColor =
    OUTCOME_STYLES[event.outcome.toUpperCase()] ?? "text-slate-400";
  const isError = event.outcome.toUpperCase() === "FAILURE" || event.outcome.toUpperCase() === "DEGRADED";

  return (
    <div
      id={`audit-event-${event.event_id}`}
      className={`
        px-4 py-2 border-b border-slate-800/40 last:border-0 
        hover:bg-slate-800/20 transition-colors duration-150
        ${isError ? "bg-rose-950/10" : ""}
        ${index === 0 ? "animate-in fade-in slide-in-from-bottom-2 duration-300" : ""}
      `}
    >
      <div className="flex items-start gap-3 font-mono text-xs">
        {/* Timestamp */}
        <span className="text-slate-600 shrink-0 tabular-nums pt-0.5">
          {formatTime(event.occurred_at)}
        </span>

        {/* Actor */}
        <span className="text-indigo-400/80 shrink-0 max-w-[100px] truncate" title={event.actor}>
          [{event.actor}]
        </span>

        {/* Action */}
        <span className="text-slate-300 font-medium">{event.action}</span>

        {/* Outcome */}
        <span className={`ml-auto shrink-0 font-bold ${outcomeColor}`}>
          {event.outcome}
        </span>
      </div>

      {/* Details */}
      {Object.keys(event.details).length > 0 && (
        <div className="ml-[calc(3.5rem+1.5rem)] mt-0.5">
          {Object.entries(event.details).map(([k, v]) => (
            <span key={k} className="text-[10px] text-slate-600 mr-3">
              <span className="text-slate-500">{k}=</span>
              <span className="text-slate-400">{String(v)}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// -------------------------------------------------------------------------
// Component
// -------------------------------------------------------------------------

interface AuditTrailProps {
  planId: string;
}

export default function AuditTrail({ planId }: AuditTrailProps) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isDegraded, setIsDegraded] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const seenIds = useRef(new Set<string>());
  const scrollRef = useRef<HTMLDivElement>(null);
  const isAutoScroll = useRef(true);

  const fetchEvents = useCallback(async () => {
    try {
      const fetched = await getAuditEvents(planId);
      const newEvents: AuditEvent[] = [];
      for (const evt of fetched) {
        if (!seenIds.current.has(evt.event_id)) {
          seenIds.current.add(evt.event_id);
          newEvents.push(evt);
        }
      }
      if (newEvents.length > 0) {
        setEvents((prev) => {
          // Append new events in chronological order; cap at 500 to prevent DOM bloat
          const combined = [...prev, ...newEvents];
          return combined.slice(-500);
        });
      }
      setFetchError(null);
      setIsDegraded(false);
      setLastUpdated(new Date());
    } catch (err: unknown) {
      const e = err as ApiError;
      const msg = e?.message ?? "Failed to fetch audit events";
      setFetchError(msg);
      if (e?.isDegraded) setIsDegraded(true);
    } finally {
      setIsLoading(false);
    }
  }, [planId]);

  // Initial fetch + polling
  useEffect(() => {
    fetchEvents();
    const interval = setInterval(fetchEvents, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchEvents]);

  // Auto-scroll to bottom when new events arrive (unless user scrolled up)
  useEffect(() => {
    if (!isAutoScroll.current || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [events]);

  function handleScroll() {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    // Consider auto-scroll "active" if within 40px of bottom
    isAutoScroll.current = scrollHeight - scrollTop - clientHeight < 40;
  }

  return (
    <div
      id="audit-trail"
      className="flex flex-col h-full bg-slate-950/90 backdrop-blur-md 
                 border border-slate-800/60 rounded-2xl overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/60 bg-slate-900/60">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-emerald-400" />
          <h2 className="text-sm font-bold text-slate-100 font-mono">
            Audit Trail
          </h2>
          {isDegraded && (
            <span className="flex items-center gap-1 text-xs text-red-400 font-medium bg-red-950/50 border border-red-800/40 px-2 py-0.5 rounded-full">
              <WifiOff className="h-3 w-3" />
              DEGRADED
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-600 font-mono">
            {events.length} event{events.length !== 1 ? "s" : ""}
          </span>
          {lastUpdated && (
            <span className="text-[10px] text-slate-700 font-mono">
              {formatTime(lastUpdated.toISOString())}
            </span>
          )}
          <button
            id="audit-refresh-btn"
            onClick={fetchEvents}
            className="p-1 rounded-md hover:bg-slate-800/60 text-slate-500 hover:text-slate-300 transition-colors"
            title="Refresh now"
            aria-label="Refresh audit trail"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Fetch error banner */}
      {fetchError && (
        <div
          id="audit-error-banner"
          className={`flex items-center gap-2 px-4 py-2 text-xs font-medium border-b
                     ${isDegraded
                       ? "bg-red-950/60 border-red-900/60 text-red-300"
                       : "bg-rose-950/40 border-rose-900/40 text-rose-400"
                     }`}
        >
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          {isDegraded && (
            <span className="font-bold uppercase tracking-wider mr-1">
              System Degraded —{" "}
            </span>
          )}
          {fetchError}
          <span className="text-[10px] opacity-60 ml-1">
            (retrying in {POLL_INTERVAL_MS / 1000}s)
          </span>
        </div>
      )}

      {/* Event list */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto overscroll-contain"
      >
        {isLoading && events.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2 text-slate-600">
            <RefreshCw className="h-5 w-5 animate-spin" />
            <p className="text-xs font-mono">Fetching audit events…</p>
          </div>
        ) : events.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2 text-slate-600">
            <Terminal className="h-5 w-5" />
            <p className="text-xs font-mono">No events yet. Polling…</p>
          </div>
        ) : (
          <div>
            {/* Reversed so newest appears at top when auto-scrolled to bottom */}
            {events.map((evt, i) => (
              <AuditEventRow
                key={evt.event_id}
                event={evt}
                index={i === events.length - 1 ? 0 : i + 1}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-slate-800/40 flex items-center gap-2">
        <div className={`h-1.5 w-1.5 rounded-full ${isDegraded ? "bg-red-500" : "bg-emerald-500"} animate-pulse`} />
        <p className="text-[10px] text-slate-600 font-mono">
          Polling every {POLL_INTERVAL_MS / 1000}s ·{" "}
          entity_id={planId.slice(0, 8)}…
        </p>
      </div>
    </div>
  );
}
