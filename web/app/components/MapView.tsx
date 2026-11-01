"use client";
import "maplibre-gl/dist/maplibre-gl.css";

// app/components/MapView.tsx
// MapLibre GL map rendering the route LineString and hazard polygons.
// STRICT RULE: Hazard polygons MUST be labelled "Modeled Forecast Risk"
// NEVER "road closed" or "guaranteed safe".

import React, { useEffect, useRef, useCallback } from "react";
import type { DeliveryPlan, GeoJSONPolygon } from "@/app/types/api";
import { AlertTriangle } from "lucide-react";
import maplibregl from "maplibre-gl";

// -------------------------------------------------------------------------
// Helpers
// -------------------------------------------------------------------------

function latLonToLngLat(ll: { latitude: number; longitude: number }): [number, number] {
  return [ll.longitude, ll.latitude];
}

/** Normalise a raw geometry or Feature into a GeoJSON Feature */
function toFeature(poly: GeoJSONPolygon | any): GeoJSON.Feature {
  if (poly && poly.type === "Feature") return poly as GeoJSON.Feature;
  return {
    type: "Feature",
    geometry: poly?.geometry ?? poly,
    properties: poly?.properties ?? {},
  };
}

// -------------------------------------------------------------------------
// Component
// -------------------------------------------------------------------------

interface MapViewProps {
  plan: DeliveryPlan;
}

export default function MapView({ plan }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any | null>(null);
  const initializedRef = useRef(false);

  const initMap = useCallback(() => {
    if (initializedRef.current || !containerRef.current) return;
    initializedRef.current = true;

    maplibregl.workerUrl = "https://unpkg.com/maplibre-gl@latest/dist/maplibre-gl-csp-worker.js";

    const origin = latLonToLngLat(plan.origin);
    const destination = latLonToLngLat(plan.destination);
    const center: [number, number] = [
      (origin[0] + destination[0]) / 2,
      (origin[1] + destination[1]) / 2,
    ];

    const map = new maplibregl.Map({
      container: containerRef.current!,
      maxZoom: 18,
      style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      center,
      zoom: 9,
    });

    mapRef.current = map;

    const setupLayers = () => {
      try {
        // ----------------------------------------------------------------
        // Hazard Polygons — rendered BELOW the route for clarity
        // NOTE: Do NOT use line-dasharray; it causes WebGL shader errors.
        // ----------------------------------------------------------------
        const rawPolygons: any[] =
          plan.hazard_polygons ||
          (plan as any).hazard_zones ||
          (plan as any).hazards ||
          (plan as any).hazard_assessment?.polygons ||
          (plan.route as any)?.avoid_polygons ||
          [];

        if (rawPolygons.length > 0) {
          const features = rawPolygons.map(toFeature);

          map.addSource("hazards", {
            type: "geojson",
            data: {
              type: "FeatureCollection",
              features,
            } as GeoJSON.FeatureCollection,
          });

          // Filled polygon
          map.addLayer({
            id: "hazard-fill",
            type: "fill",
            source: "hazards",
            paint: {
              "fill-color": "#ef4444",
              "fill-opacity": 0.4,
            },
          });

          // Solid outline (NO dasharray — causes WebGL errors)
          map.addLayer({
            id: "hazard-outline",
            type: "line",
            source: "hazards",
            paint: {
              "line-color": "#ef4444",
              "line-width": 2,
              "line-opacity": 0.9,
            },
          });
        }

        // ----------------------------------------------------------------
        // Route LineString
        // ----------------------------------------------------------------
        const routeGeometry = plan.route?.geometry as any;
        if (routeGeometry) {
          const routeData: GeoJSON.Feature =
            routeGeometry.type === "Feature" || routeGeometry.type === "FeatureCollection"
              ? routeGeometry
              : {
                  type: "Feature",
                  geometry: routeGeometry,
                  properties: {},
                };

          map.addSource("route", {
            type: "geojson",
            data: routeData,
          });

          // Soft glow beneath the route line
          map.addLayer({
            id: "route-glow",
            type: "line",
            source: "route",
            paint: {
              "line-color": "#38bdf8",
              "line-width": 10,
              "line-blur": 5,
              "line-opacity": 0.35,
            },
            layout: { "line-cap": "round", "line-join": "round" },
          });

          // Sharp inner route line — blue, width 5 as specified
          map.addLayer({
            id: "route-line",
            type: "line",
            source: "route",
            paint: {
              "line-color": "#3b82f6",
              "line-width": 5,
            },
            layout: { "line-cap": "round", "line-join": "round" },
          });
        }

        // ----------------------------------------------------------------
        // Markers
        // ----------------------------------------------------------------
        new maplibregl.Marker({ color: "#22c55e", scale: 1.1 })
          .setLngLat(origin)
          .setPopup(
            new maplibregl.Popup({ offset: 25 }).setHTML(
              `<div style="color:#111;font-size:13px;font-weight:600">📦 Origin (Electronic City)</div>
               <div style="color:#333;font-size:11px">${plan.origin.latitude.toFixed(4)}, ${plan.origin.longitude.toFixed(4)}</div>`
            )
          )
          .addTo(map);

        new maplibregl.Marker({ color: "#f59e0b", scale: 1.1 })
          .setLngLat(destination)
          .setPopup(
            new maplibregl.Popup({ offset: 25 }).setHTML(
              `<div style="color:#111;font-size:13px;font-weight:600">🏥 Destination (Anekal)</div>
               <div style="color:#333;font-size:11px">${plan.destination.latitude.toFixed(4)}, ${plan.destination.longitude.toFixed(4)}</div>`
            )
          )
          .addTo(map);

        // ----------------------------------------------------------------
        // Fit bounds to show both markers + route
        // ----------------------------------------------------------------
        const bounds = new maplibregl.LngLatBounds(origin, origin);
        bounds.extend(destination);
        const coords = (plan.route?.geometry as any)?.coordinates;
        if (Array.isArray(coords)) {
          for (const c of coords) {
            if (Array.isArray(c) && typeof c[0] === "number" && typeof c[1] === "number") {
              bounds.extend(c as [number, number]);
            }
          }
        }
        map.fitBounds(bounds, { padding: 80, maxZoom: 15, duration: 1000 });
        map.resize();
      } catch (err) {
        console.error("[MapView] Error setting up layers/markers:", err);
      }
    };

    // Fire immediately if style already loaded, else wait for load event
    if (map.loaded() || map.isStyleLoaded()) {
      setupLayers();
    } else {
      map.once("load", setupLayers);
    }

    return () => {
      map.remove();
      mapRef.current = null;
      initializedRef.current = false;
    };
  }, [plan]);

  useEffect(() => {
    const cleanup = initMap();
    return () => {
      cleanup?.();
    };
  }, [initMap]);

  return (
    <div className="relative w-full h-full rounded-xl overflow-hidden">
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

      {/* Map container */}
      <div ref={containerRef} className="absolute inset-0" />

      {/* MANDATORY: Modeled Forecast Risk label — never "road closed" or "guaranteed safe" */}
      <div
        id="hazard-warning-badge"
        className="absolute top-3 left-3 z-10 flex items-center gap-2
                   bg-red-950/90 border border-red-500/60 rounded-lg px-3 py-2
                   backdrop-blur-sm shadow-lg"
      >
        <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
        <div>
          <p className="text-xs font-bold text-red-300 uppercase tracking-wider">
            Modeled Forecast Risk
          </p>
          <p className="text-[10px] text-red-400/80 leading-tight">
            Polygons represent modeled risk areas only — not verified road closures
          </p>
        </div>
      </div>

      {/* Route risk badge */}
      {plan.route && (
        <div
          id="route-risk-badge"
          className="absolute bottom-3 left-3 z-10 flex items-center gap-2
                     bg-slate-900/90 border border-slate-700/60 rounded-lg px-3 py-2
                     backdrop-blur-sm shadow-lg"
        >
          <div
            className={`h-2 w-2 rounded-full ${
              plan.route.risk_level === "HIGH"
                ? "bg-red-500"
                : plan.route.risk_level === "MODERATE"
                ? "bg-amber-500"
                : plan.route.risk_level === "LOW"
                ? "bg-emerald-500"
                : "bg-slate-400"
            }`}
          />
          <span className="text-xs text-slate-300 font-medium">
            Route Risk: {plan.route.risk_level}
          </span>
          <span className="text-xs text-slate-500">•</span>
          <span className="text-xs text-slate-400">
            {(plan.route.distance_m / 1000).toFixed(1)} km
          </span>
        </div>
      )}

      {/* Attribution */}
      <div className="absolute bottom-3 right-3 z-10 text-[10px] text-slate-500 bg-slate-900/70 px-2 py-0.5 rounded">
        © OpenStreetMap contributors
      </div>
    </div>
  );
}

export type { MapViewProps };
