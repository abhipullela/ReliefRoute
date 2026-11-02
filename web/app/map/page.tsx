"use client";
import "maplibre-gl/dist/maplibre-gl.css";

// app/map/page.tsx — ReliefRoute Full-Screen Active Flood Areas Map
// Interactive MapLibre GL JS map with active flood markers (flags),
// hover tooltip displaying Plan ID, and click routing to /plan/[id].
// Supports ?mode=demo vs ?mode=live via URL search parameter.

import React, { useEffect, useRef, useState, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Radio,
  AlertTriangle,
  Layers,
  LogOut,
  RefreshCw,
  ArrowRight,
  Droplets,
  Sparkles,
  Server,
} from "lucide-react";
import { ACTIVE_FLOOD_AREAS, MOCK_PLANS } from "@/app/lib/mockData";
import { getActiveFloodAreas, getActivePlans } from "@/app/lib/api";
import type { ActiveFloodArea, DeliveryPlan } from "@/app/types/api";
import maplibregl from "maplibre-gl";

const SEVERITY_COLORS: Record<string, { bg: string; border: string; text: string; glow: string }> = {
  CRITICAL: {
    bg: "#ef4444",
    border: "#b91c1c",
    text: "text-rose-400",
    glow: "rgba(239, 68, 68, 0.45)",
  },
  HIGH: {
    bg: "#f97316",
    border: "#c2410c",
    text: "text-orange-400",
    glow: "rgba(249, 115, 22, 0.45)",
  },
  MODERATE: {
    bg: "#eab308",
    border: "#a16207",
    text: "text-amber-400",
    glow: "rgba(234, 179, 8, 0.45)",
  },
};

function MapLoadingFallback() {
  return (
    <div className="w-screen h-screen flex flex-col items-center justify-center bg-slate-950 text-slate-300 select-none">
      <div className="flex flex-col items-center gap-3">
        <div className="h-10 w-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs font-semibold tracking-wider uppercase text-slate-400">
          Initializing Flood Operations Map…
        </p>
      </div>
    </div>
  );
}

function FullScreenMapContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // URL Query Parameter Mode Detection (?mode=demo vs ?mode=live)
  const mode = searchParams.get("mode") || "live";
  const isDemo = mode === "demo";

  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any | null>(null);
  const markersRef = useRef<any[]>([]);
  const isMapLoadedRef = useRef(false);

  const [floodAreas, setFloodAreas] = useState<ActiveFloodArea[]>([]);
  const [plans, setPlans] = useState<DeliveryPlan[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [hoveredPlanId, setHoveredPlanId] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showDrawer, setShowDrawer] = useState(true);

  // Sync active plans and flood areas depending on isDemo flag
  const refreshActivePlans = useCallback(async () => {
    setIsRefreshing(true);
    try {
      if (isDemo) {
        // Pure Hackathon Demo Mode: load curated scenario plans and flood flags
        const areas = await getActiveFloodAreas(true);
        const demoPlans = await getActivePlans(true);
        setFloodAreas(areas.length > 0 ? areas : structuredClone(ACTIVE_FLOOD_AREAS));
        setPlans(demoPlans.length > 0 ? demoPlans : structuredClone(MOCK_PLANS));
      } else {
        // Real-Time Live Mode: query FastAPI backend
        const [liveAreas, livePlans] = await Promise.all([
          getActiveFloodAreas(false),
          getActivePlans(false),
        ]);

        setPlans(livePlans);

        if (liveAreas.length > 0) {
          setFloodAreas(liveAreas);
        } else if (livePlans.length > 0) {
          // Derive active flood areas from live plans returned by backend
          const derived: ActiveFloodArea[] = livePlans.map((p) => ({
            plan_id: p.plan_id,
            name: p.rationale?.[0] || `Live Emergency Relief Corridor (${p.plan_id})`,
            coordinates: [p.destination.longitude, p.destination.latitude],
            severity: p.route?.risk_level === "HIGH" ? "CRITICAL" : "HIGH",
            water_level: "Monitored Flood Ingress",
            commodity: `${p.quantity} ${p.unit} of ${p.commodity}`,
            status: p.status,
            people_affected: p.gen_ai_extraction?.people_affected || 35,
          }));
          setFloodAreas(derived);
        } else {
          // Backend returned 0 active plans in live mode
          setFloodAreas([]);
        }
      }
    } catch (err) {
      console.warn(`[Map] Failed to refresh active plans (isDemo=${isDemo}):`, err);
      if (isDemo) {
        setFloodAreas(structuredClone(ACTIVE_FLOOD_AREAS));
        setPlans(structuredClone(MOCK_PLANS));
      } else {
        setFloodAreas([]);
        setPlans([]);
      }
    } finally {
      setIsRefreshing(false);
    }
  }, [isDemo]);

  useEffect(() => {
    refreshActivePlans();
  }, [refreshActivePlans]);

  // Initialize MapLibre GL Map
  useEffect(() => {
    if (isMapLoadedRef.current || !mapContainerRef.current) return;
    isMapLoadedRef.current = true;

    maplibregl.workerUrl = "https://unpkg.com/maplibre-gl@latest/dist/maplibre-gl-csp-worker.js";

    const map = new maplibregl.Map({
      container: mapContainerRef.current!,
      style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      center: [77.72, 12.785], // Bengaluru South / Anekal pilot region
      zoom: 11,
    });

    mapInstanceRef.current = map;

    map.on("load", () => {
      // Collect hazard polygons from demo or live plans
      const sourcePlans = isDemo ? MOCK_PLANS : plans;
      const allPolygons: GeoJSON.Feature[] = [];

      sourcePlans.forEach((plan) => {
        if (plan.hazard_polygons && plan.hazard_polygons.length > 0) {
          plan.hazard_polygons.forEach((poly) => {
            allPolygons.push({
              type: "Feature",
              geometry: poly,
              properties: { plan_id: plan.plan_id },
            });
          });
        }
      });

      if (allPolygons.length > 0 && !map.getSource("flood-hazard-zones")) {
        map.addSource("flood-hazard-zones", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: allPolygons,
          } as GeoJSON.FeatureCollection,
        });

        // Translucent fill for active flood zones
        map.addLayer({
          id: "flood-hazard-fill",
          type: "fill",
          source: "flood-hazard-zones",
          paint: {
            "fill-color": "#ef4444",
            "fill-opacity": 0.28,
          },
        });

        // Solid perimeter outline
        map.addLayer({
          id: "flood-hazard-outline",
          type: "line",
          source: "flood-hazard-zones",
          paint: {
            "line-color": "#dc2626",
            "line-width": 2.5,
            "line-opacity": 0.85,
          },
        });
      }
    });
  }, [isDemo, plans]);

  // Update Markers whenever floodAreas changes or map is ready
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    // Clear previous markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    floodAreas.forEach((area) => {
      const severity = SEVERITY_COLORS[area.severity] || SEVERITY_COLORS.HIGH;

      // Create Custom Flag Marker DOM Element
      const el = document.createElement("div");
      el.className = "cursor-pointer";
      el.style.cssText = `
        width: 44px;
        height: 48px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: flex-start;
        cursor: pointer;
      `;

      // Inner HTML: High-visibility Emergency Flag Pin with Pulsing Ripple Ring
      el.innerHTML = `
        <div style="
          position: absolute;
          bottom: 4px;
          width: 22px;
          height: 8px;
          background: rgba(0,0,0,0.4);
          border-radius: 50%;
          filter: blur(2px);
        "></div>
        <div style="
          position: absolute;
          bottom: 4px;
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: ${severity.glow};
          animation: ping 1.8s cubic-bezier(0, 0, 0.2, 1) infinite;
          pointer-events: none;
        "></div>
        <div style="
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 38px;
          height: 38px;
          background: linear-gradient(135deg, ${severity.bg}, ${severity.border});
          border: 2.5px solid #ffffff;
          border-radius: 12px 12px 12px 2px;
          box-shadow: 0 8px 20px rgba(0,0,0,0.5), 0 0 14px ${severity.glow};
          transform: rotate(-5deg);
        ">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"></path>
            <line x1="4" y1="22" x2="4" y2="15"></line>
          </svg>
        </div>
        <div style="
          position: absolute;
          top: -6px;
          right: -4px;
          background: #0f172a;
          color: #f8fafc;
          border: 1.5px solid ${severity.border};
          border-radius: 6px;
          padding: 1px 4px;
          font-size: 9px;
          font-weight: 800;
          font-family: monospace;
          box-shadow: 0 2px 6px rgba(0,0,0,0.4);
        ">
          ${area.plan_id.replace("PLAN-", "")}
        </div>
      `;

      // Tooltip using standard MapLibre GL Popup
      const popup = new maplibregl.Popup({
        offset: [0, -32],
        closeButton: false,
        closeOnClick: false,
        className: "flood-plan-tooltip",
      }).setHTML(`
        <div style="background:#090d16; color:#f8fafc; border:1px solid rgba(99,102,241,0.3); border-radius:12px; padding:12px 14px; min-width:240px; box-shadow:0 12px 30px rgba(0,0,0,0.7); font-family:sans-serif;">
          <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:6px;">
            <div style="display:flex; align-items:center; gap:6px;">
              <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${severity.bg};"></span>
              <span style="font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:0.05em; color:#94a3b8;">Active Flood Zone</span>
            </div>
            <span style="font-size:10px; font-weight:700; background:rgba(255,255,255,0.1); color:#e2e8f0; padding:2px 6px; border-radius:4px;">
              ${area.status}
            </span>
          </div>

          <div style="margin-bottom:8px;">
            <div style="font-size:11px; color:#94a3b8; font-weight:600;">Associated Plan ID:</div>
            <div style="font-size:14px; font-weight:800; font-family:monospace; color:#38bdf8; letter-spacing:0.02em;">
              ${area.plan_id}
            </div>
          </div>

          <div style="font-size:13px; font-weight:700; color:#ffffff; margin-bottom:3px;">
            ${area.name}
          </div>

          <div style="font-size:11px; color:#cbd5e1; margin-bottom:8px; line-height:1.4;">
            🌊 ${area.water_level} · 📦 ${area.commodity}
          </div>

          <div style="display:flex; align-items:center; justify-content:space-between; margin-top:8px; padding-top:6px; border-top:1px dashed rgba(255,255,255,0.15); font-size:11px; font-weight:600; color:#818cf8;">
            <span>Click to view delivery plan (${isDemo ? "Demo" : "Live"})</span>
            <span>→</span>
          </div>
        </div>
      `);

      // Hover interaction: display tooltip showing Plan ID without modifying element transforms
      el.addEventListener("mouseenter", () => {
        setHoveredPlanId(area.plan_id);
        popup.setLngLat(area.coordinates).addTo(map);
      });

      el.addEventListener("mouseleave", () => {
        setHoveredPlanId(null);
        popup.remove();
      });

      // Click interaction: push user to /plan/[id]?mode=...
      el.addEventListener("click", () => {
        router.push(`/plan/${encodeURIComponent(area.plan_id)}?mode=${isDemo ? "demo" : "live"}`);
      });

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat(area.coordinates)
        .addTo(map);

      markersRef.current.push(marker);
    });
  }, [floodAreas, router, isDemo]);

  // Center map on a selected area
  function handleFocusArea(area: ActiveFloodArea) {
    setSelectedPlanId(area.plan_id);
    if (mapInstanceRef.current) {
      mapInstanceRef.current.flyTo({
        center: area.coordinates,
        zoom: 13,
        essential: true,
      });
    }
  }

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-slate-950 text-slate-100 select-none">
      {/* MapLibre Popup Global Override */}
      <style>{`
        .maplibregl-popup-content {
          background: transparent !important;
          padding: 0 !important;
          box-shadow: none !important;
        }
        .maplibregl-popup-tip {
          display: none !important;
        }
      `}</style>

      {/* Map Container */}
      <div ref={mapContainerRef} className="absolute inset-0 w-full h-full z-0" />

      {/* ----------------------------------------------------------------- */}
      {/* Top Floating Command HUD                                          */}
      {/* ----------------------------------------------------------------- */}
      <header className="absolute top-4 left-4 right-4 z-20 flex items-center justify-between pointer-events-none gap-3">
        {/* Brand & Stats Bar */}
        <div className="flex items-center gap-3 bg-slate-900/90 backdrop-blur-xl border border-slate-800/80 rounded-2xl px-4 py-2.5 shadow-2xl pointer-events-auto">
          <div className="flex items-center justify-center h-8 w-8 rounded-xl bg-indigo-600/20 border border-indigo-500/40 text-indigo-400">
            <Radio className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-black text-slate-100 tracking-tight">
                ReliefRoute
              </h1>

              {/* Mode Badge Indicator */}
              {isDemo ? (
                <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider bg-indigo-950/70 text-indigo-300 border border-indigo-700/60 rounded-full px-2 py-0.5">
                  <Sparkles className="h-2.5 w-2.5 text-indigo-400" />
                  Demo Mode
                </span>
              ) : (
                <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider bg-emerald-950/70 text-emerald-400 border border-emerald-700/60 rounded-full px-2 py-0.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
                  Live Ops (FastAPI)
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-400 hidden sm:block">
              Full-Screen Flood Surveillance & Dispatch Map
            </p>
          </div>

          <div className="h-5 w-px bg-slate-800 mx-1 hidden sm:block" />

          {/* Active Flood Areas Badge */}
          <div className="hidden sm:flex items-center gap-2 bg-rose-950/40 border border-rose-800/40 rounded-xl px-2.5 py-1 text-xs">
            <span className="h-2 w-2 rounded-full bg-rose-500" />
            <span className="font-semibold text-rose-300">
              {floodAreas.length} Active Flood Flags
            </span>
          </div>
        </div>

        {/* Right Action Bar */}
        <div className="flex items-center gap-2 pointer-events-auto">
          {/* Mode Switcher Quick Button */}
          <button
            onClick={() => {
              const nextMode = isDemo ? "live" : "demo";
              router.push(`/map?mode=${nextMode}`);
            }}
            className={`flex items-center gap-1.5 backdrop-blur-xl border rounded-xl px-3 py-2 text-xs font-semibold transition-all shadow-xl cursor-pointer ${
              isDemo
                ? "bg-slate-900/90 hover:bg-emerald-950/50 border-slate-700 text-slate-300 hover:text-emerald-300 hover:border-emerald-700"
                : "bg-slate-900/90 hover:bg-indigo-950/50 border-slate-700 text-slate-300 hover:text-indigo-300 hover:border-indigo-700"
            }`}
            title={isDemo ? "Switch to Real-Time FastAPI Live Mode" : "Switch to Hackathon Demo Scenarios"}
          >
            {isDemo ? (
              <>
                <Server className="h-3.5 w-3.5 text-emerald-400" />
                <span className="hidden lg:inline">Switch to Live Ops</span>
              </>
            ) : (
              <>
                <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                <span className="hidden lg:inline">Switch to Demo Mode</span>
              </>
            )}
          </button>

          {/* Refresh button */}
          <button
            onClick={refreshActivePlans}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 bg-slate-900/90 hover:bg-slate-800/90 backdrop-blur-xl border border-slate-800/80 rounded-xl px-3 py-2 text-xs font-semibold text-slate-300 hover:text-white transition-all shadow-xl cursor-pointer"
            title="Refresh active flood reports"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`}
            />
            <span className="hidden md:inline">Sync Data</span>
          </button>

          {/* Toggle Flood List Drawer */}
          <button
            onClick={() => setShowDrawer((prev) => !prev)}
            className="flex items-center gap-1.5 bg-slate-900/90 hover:bg-slate-800/90 backdrop-blur-xl border border-slate-800/80 rounded-xl px-3 py-2 text-xs font-semibold text-slate-300 hover:text-white transition-all shadow-xl cursor-pointer"
          >
            <Layers className="h-3.5 w-3.5 text-indigo-400" />
            <span className="hidden sm:inline">
              {showDrawer ? "Hide List" : "Show List"}
            </span>
          </button>

          {/* Exit / Return to Login */}
          <button
            onClick={() => router.push("/")}
            className="flex items-center gap-1.5 bg-slate-900/90 hover:bg-rose-950/60 backdrop-blur-xl border border-slate-800/80 hover:border-rose-800/50 rounded-xl px-3 py-2 text-xs font-semibold text-slate-300 hover:text-rose-200 transition-all shadow-xl cursor-pointer"
            title="Sign out to login"
          >
            <LogOut className="h-3.5 w-3.5" />
            <span className="hidden md:inline">Sign Out</span>
          </button>
        </div>
      </header>

      {/* ----------------------------------------------------------------- */}
      {/* Forecast Risk Advisory Banner                                    */}
      {/* ----------------------------------------------------------------- */}
      <div className="absolute top-20 left-1/2 -translate-x-1/2 z-10 pointer-events-none max-w-xl w-[90%] sm:w-auto">
        <div className="flex items-center justify-center gap-2 bg-slate-900/80 backdrop-blur-md border border-amber-500/30 text-amber-300/90 rounded-full px-4 py-1.5 text-xs shadow-xl text-center pointer-events-auto">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
          <span>
            {isDemo ? (
              <>
                <span className="font-bold text-indigo-300">Demo Scenario Active:</span> Showing 5 pre-configured flood emergency scenarios.
              </>
            ) : (
              <>
                <span className="font-bold text-emerald-300">Live Backend Connected:</span> Real-time telemetry from FastAPI & PostgreSQL.
              </>
            )}
          </span>
        </div>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Active Flood Areas List Drawer (Floating Bottom-Left)             */}
      {/* ----------------------------------------------------------------- */}
      {showDrawer && (
        <aside className="absolute bottom-6 left-4 z-20 w-80 sm:w-96 max-h-[50vh] flex flex-col bg-slate-900/95 backdrop-blur-2xl border border-slate-800/80 rounded-2xl shadow-2xl overflow-hidden transition-all duration-300">
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/80 bg-slate-900/60">
            <div className="flex items-center gap-2">
              <Droplets className="h-4 w-4 text-sky-400" />
              <h2 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                {isDemo ? "Demo Flood Areas" : "Live Flood Areas"}
              </h2>
            </div>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-400">
              {floodAreas.length} sites
            </span>
          </div>

          <div className="overflow-y-auto p-2 space-y-1.5 flex-1 divide-y divide-slate-800/40">
            {floodAreas.length === 0 ? (
              <div className="p-6 text-center text-slate-500 text-xs">
                {isDemo
                  ? "No demo flood areas loaded."
                  : "No live active plans returned from FastAPI. Switch to Demo Mode to test pre-seeded scenarios."}
              </div>
            ) : (
              floodAreas.map((area) => {
                const severity =
                  SEVERITY_COLORS[area.severity] || SEVERITY_COLORS.HIGH;
                const isHovered = hoveredPlanId === area.plan_id;

                return (
                  <div
                    key={area.plan_id}
                    onClick={() =>
                      router.push(
                        `/plan/${encodeURIComponent(area.plan_id)}?mode=${
                          isDemo ? "demo" : "live"
                        }`
                      )
                    }
                    onMouseEnter={() => handleFocusArea(area)}
                    className={`pt-1.5 p-2.5 rounded-xl transition-all cursor-pointer border ${
                      isHovered || selectedPlanId === area.plan_id
                        ? "bg-slate-800/80 border-indigo-500/50 shadow-md ring-1 ring-indigo-500/30"
                        : "bg-slate-950/40 border-slate-800/60 hover:bg-slate-800/40 hover:border-slate-700/60"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span
                            className="h-2 w-2 rounded-full shrink-0"
                            style={{ background: severity.bg }}
                          />
                          <span className="font-mono text-xs font-bold text-sky-400">
                            {area.plan_id}
                          </span>
                          <span className="text-[10px] font-semibold text-slate-400 bg-slate-800/90 rounded px-1.5 py-0.2">
                            {area.status}
                          </span>
                        </div>
                        <p className="text-xs font-semibold text-slate-200 truncate mt-0.5">
                          {area.name}
                        </p>
                      </div>

                      <div className="shrink-0 flex items-center gap-1 text-[11px] font-semibold text-indigo-400 group-hover:text-indigo-300">
                        <span>View</span>
                        <ArrowRight className="h-3 w-3" />
                      </div>
                    </div>

                    <div className="flex items-center gap-2 mt-2 text-[11px] text-slate-400">
                      <span className="truncate">📦 {area.commodity}</span>
                      <span>·</span>
                      <span className="shrink-0 text-slate-500">
                        👥 {area.people_affected} affected
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div className="p-2.5 border-t border-slate-800/80 bg-slate-950/70 text-center">
            <p className="text-[11px] text-slate-500">
              Hover over a marker on the map to see its Plan ID or click to open.
            </p>
          </div>
        </aside>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Map Legend (Bottom Right)                                         */}
      {/* ----------------------------------------------------------------- */}
      <div className="absolute bottom-6 right-4 z-20 hidden sm:flex flex-col gap-1.5 bg-slate-900/90 backdrop-blur-xl border border-slate-800/80 rounded-xl p-3 shadow-xl text-xs text-slate-300">
        <div className="font-bold text-[11px] text-slate-400 uppercase tracking-wider mb-0.5">
          Map Legend ({isDemo ? "Demo Mode" : "Live Ops"})
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-rose-600 flex items-center justify-center text-[10px] text-white">
            🚩
          </div>
          <span>Active Flood Area (Click to Open)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-3 rounded bg-red-500/30 border border-red-500" />
          <span>Modeled Forecast Risk Polygon</span>
        </div>
        <div className="flex items-center gap-2 text-slate-400 text-[10px] mt-1 pt-1 border-t border-slate-800">
          <span>Coordinates: Anekal / Bengaluru South Pilot</span>
        </div>
      </div>
    </div>
  );
}

export default function FullScreenMapPage() {
  return (
    <Suspense fallback={<MapLoadingFallback />}>
      <FullScreenMapContent />
    </Suspense>
  );
}
