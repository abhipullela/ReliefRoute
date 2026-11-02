// app/lib/api.ts
// Typed API client connecting to the live FastAPI server,
// with robust mockData.ts fallback for the hackathon demo.

import type {
  DeliveryPlan,
  ApprovalRequest,
  DispatchRequest,
  DispatchResult,
  AuditEvent,
  ApiErrorResponse,
  ActiveFloodArea,
} from "@/app/types/api";
import {
  MOCK_PLANS,
  ACTIVE_FLOOD_AREAS,
  MOCK_REPORTS,
  CitizenReport,
} from "@/app/lib/mockData";

// 1. Live FastAPI Backend Base URL
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export { API_BASE_URL };

// -------------------------------------------------------------------------
// Custom error (kept for compatibility with UI callers)
// -------------------------------------------------------------------------

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly isConflict: boolean;
  readonly isDegraded: boolean;

  constructor(status: number, body: ApiErrorResponse) {
    super(body.message ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code ?? "UNKNOWN";
    this.retryable = body.retryable ?? false;
    this.isConflict = status === 409;
    this.isDegraded = status === 502 || status === 503 || status === 504;
  }
}

// -------------------------------------------------------------------------
// In-memory fallback cache
// -------------------------------------------------------------------------

const localPlanStore = new Map<string, DeliveryPlan>();

// Seed in-memory store with all mock plans
for (const plan of MOCK_PLANS) {
  localPlanStore.set(plan.plan_id.toLowerCase(), plan);
}

// Test plan seed
const MOCK_TEST_PLAN: DeliveryPlan = {
  plan_id: "test",
  created_at: new Date().toISOString(),
  supplier_id: "supplier-electronic-city-01",
  commodity: "Emergency Medical Kits & Water Purification Packs",
  quantity: 450,
  unit: "crates",
  origin: { latitude: 12.8442, longitude: 77.6648 },
  destination: { latitude: 12.7112, longitude: 77.6954 },
  status: "PENDING_APPROVAL",
  approval_required: true,
  idempotency_key: "idemp-test-plan-001",
  hazard_assessment_id: "haz-assess-flood-test",
  rationale: [
    "Heavy precipitation (>45mm/hr) detected along regional secondary routes.",
    "Rerouted via primary arterial bypass (Hosur Rd / SH-87) to circumvent active flood hazard polygon.",
    "Human-in-the-loop approval gate triggered: risk classification exceeds autonomous threshold.",
  ],
  source_refs: [
    {
      provider: "Open-Meteo & Central Water Commission",
      url: "https://api.open-meteo.com",
      retrieved_at: new Date().toISOString(),
      stale: false,
      notes: "Modeled flood risk and precipitation forecast",
    },
  ],
  route: {
    provider: "openrouteservice",
    geometry: {
      type: "LineString",
      coordinates: [
        [77.6648, 12.8442],
        [77.6715, 12.836],
        [77.678, 12.825],
        [77.686, 12.812],
        [77.694, 12.798],
        [77.698, 12.775],
        [77.701, 12.752],
        [77.7025, 12.731],
        [77.6954, 12.7112],
      ],
    },
    distance_m: 18450,
    duration_s: 1620,
    avoids_requested_polygons: true,
    risk_level: "MODERATE",
    warnings: [
      "Modeled flood risk zone nearby along Chandapura-Muthanallur basin",
      "Surface runoff advisory active",
    ],
    source: {
      provider: "openrouteservice",
      retrieved_at: new Date().toISOString(),
      stale: false,
    },
  },
  hazard_polygons: [
    {
      type: "Polygon",
      coordinates: [
        [
          [77.682, 12.805],
          [77.712, 12.805],
          [77.718, 12.775],
          [77.688, 12.77],
          [77.682, 12.805],
        ],
      ],
    },
  ],
  gen_ai_extraction: {
    emergency_type: "FLASH FLOOD & MEDICAL DISTRESS",
    requested_supplies: [
      "Drinking Water Purification Packs",
      "Emergency Medical Trauma Kits",
    ],
    extracted_location: "Anekal Basin Relief Sector (SH-87 Junction)",
    original_message:
      "Heavy precipitation >45mm/hr detected along secondary routes. Multiple families isolated, urgent medical and water support needed.",
    confidence: 97.4,
    people_affected: 450,
  },
};
localPlanStore.set("test", MOCK_TEST_PLAN);

function synthesizePlan(planId: string): DeliveryPlan {
  return {
    plan_id: planId,
    created_at: new Date().toISOString(),
    supplier_id: "supplier-electronic-city-01",
    commodity: "Emergency Drinking Water & Medical Trauma Kits",
    quantity: 350,
    unit: "crates",
    origin: { latitude: 12.8442, longitude: 77.6648 },
    destination: { latitude: 12.785, longitude: 77.71 },
    status: "NEEDS_APPROVAL",
    approval_required: true,
    idempotency_key: `idemp-${planId}`,
    hazard_assessment_id: `haz-${planId}`,
    rationale: [
      `Emergency plan automatically synthesized from citizen report (${planId}).`,
      "Severe modeled forecast flood risk detected along low-lying drainage corridors.",
      "Human-in-the-loop approval gate triggered before driver dispatch.",
    ],
    source_refs: [
      {
        provider: "ReliefRoute Gen AI Dispatch & Open-Meteo",
        url: "https://api.open-meteo.com",
        retrieved_at: new Date().toISOString(),
        stale: false,
        notes: "Modeled forecast risk",
      },
    ],
    route: {
      provider: "openrouteservice",
      geometry: {
        type: "LineString",
        coordinates: [
          [77.6648, 12.8442],
          [77.675, 12.83],
          [77.69, 12.815],
          [77.71, 12.785],
        ],
      },
      distance_m: 11200,
      duration_s: 1280,
      avoids_requested_polygons: true,
      risk_level: "MODERATE",
      warnings: ["Active flood hazard advisory active along regional drainage basin"],
      source: {
        provider: "openrouteservice",
        retrieved_at: new Date().toISOString(),
        stale: false,
      },
    },
    hazard_polygons: [
      {
        type: "Polygon",
        coordinates: [
          [
            [77.695, 12.795],
            [77.725, 12.795],
            [77.73, 12.77],
            [77.7, 12.768],
            [77.695, 12.795],
          ],
        ],
      },
    ],
    gen_ai_extraction: {
      emergency_type: "ACTIVE FLOOD INUNDATION",
      requested_supplies: ["Clean Drinking Water", "Medical Trauma Kits"],
      extracted_location: `Regional Pilot Sector (${planId})`,
      original_message: `Natural language emergency report received for ${planId}: flooding reported with requests for emergency medical and water supplies.`,
      confidence: 95.8,
      people_affected: 35,
    },
  };
}

// -------------------------------------------------------------------------
// Helper: multi-path fetch for FastAPI endpoints (tries direct & /api/v1 paths)
// -------------------------------------------------------------------------

async function tryFetch<T>(primaryPath: string, altPath?: string, options?: RequestInit): Promise<T> {
  let res = await fetch(`${API_BASE_URL}${primaryPath}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options?.headers || {}),
    },
    cache: "no-store",
  });

  if (!res.ok && altPath) {
    try {
      const altRes = await fetch(`${API_BASE_URL}${altPath}`, {
        ...options,
        headers: {
          Accept: "application/json",
          ...(options?.headers || {}),
        },
        cache: "no-store",
      });
      if (altRes.ok) {
        res = altRes;
      }
    } catch {
      // Keep original res
    }
  }

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }

  return (await res.json()) as T;
}

// -------------------------------------------------------------------------
// Public API Functions (Bifurcated: Live Backend vs. Demo Mock Mode)
// -------------------------------------------------------------------------

/**
 * Fetch all active delivery plans.
 * If isDemo is true, returns curated mock scenario plans immediately.
 * If isDemo is false, queries the live FastAPI backend at API_BASE_URL.
 */
export async function getActivePlans(isDemo: boolean = false): Promise<DeliveryPlan[]> {
  if (isDemo) {
    console.info("[API:Demo] Using curated scenario delivery plans.");
    return structuredClone(MOCK_PLANS);
  }

  try {
    console.info(`[API:Live] Fetching active plans from ${API_BASE_URL}/api/plans...`);
    const data = await tryFetch<DeliveryPlan[]>("/api/plans", "/plans");
    if (Array.isArray(data) && data.length > 0) {
      data.forEach((p: DeliveryPlan) => {
        localPlanStore.set(p.plan_id.toLowerCase(), p);
      });
      return data;
    }
    return [];
  } catch (err) {
    console.warn(
      `[API:Live] Live backend (${API_BASE_URL}) returned no active plans or is unreachable:`,
      err
    );
    // In live mode, return empty list to reflect real backend state
    return [];
  }
}

// Export alias for callers using fetchActivePlans
export const fetchActivePlans = getActivePlans;

/**
 * Fetch active flood areas for the map view.
 * If isDemo is true, returns curated mock flood areas.
 * If isDemo is false, attempts live fetch or derives from live active plans.
 */
export async function getActiveFloodAreas(isDemo: boolean = false): Promise<ActiveFloodArea[]> {
  if (isDemo) {
    console.info("[API:Demo] Using curated scenario flood areas.");
    return structuredClone(ACTIVE_FLOOD_AREAS);
  }

  try {
    console.info(`[API:Live] Fetching live flood areas from ${API_BASE_URL}/api/flood-areas...`);
    const data = await tryFetch<ActiveFloodArea[]>("/api/flood-areas", "/flood-areas");
    if (Array.isArray(data) && data.length > 0) {
      return data;
    }
    return [];
  } catch (err) {
    console.warn(
      `[API:Live] Live flood areas unavailable from backend (${API_BASE_URL}):`,
      err
    );
    return [];
  }
}

// Export alias for callers using fetchActiveFloodAreas
export const fetchActiveFloodAreas = getActiveFloodAreas;

/**
 * Fetch a specific DeliveryPlan by ID.
 * If isDemo is true, looks up the plan from mock scenarios or local store.
 * If isDemo is false, queries the live FastAPI backend.
 */
export async function getPlan(planId: string, isDemo: boolean = false): Promise<DeliveryPlan> {
  const normalized = planId.trim().toLowerCase();

  // 1. Demo Mode: return curated scenario mock data
  if (isDemo) {
    if (localPlanStore.has(normalized)) {
      return structuredClone(localPlanStore.get(normalized)!);
    }

    const foundMock = MOCK_PLANS.find(
      (p) => p.plan_id.toLowerCase() === normalized
    );
    if (foundMock) {
      localPlanStore.set(normalized, foundMock);
      return structuredClone(foundMock);
    }

    if (typeof window !== "undefined") {
      try {
        const stored = localStorage.getItem(`reliefroute_plan_${normalized}`);
        if (stored) {
          const parsed = JSON.parse(stored) as DeliveryPlan;
          localPlanStore.set(normalized, parsed);
          return structuredClone(parsed);
        }
      } catch {
        // Ignore localStorage error
      }
    }

    const synthesized = synthesizePlan(planId);
    localPlanStore.set(normalized, synthesized);
    return structuredClone(synthesized);
  }

  // 2. Live Mode: Query FastAPI backend GET /api/plans/{id}
  try {
    const encoded = encodeURIComponent(planId);
    const plan = await tryFetch<DeliveryPlan>(`/api/plans/${encoded}`, `/plans/${encoded}`);
    localPlanStore.set(normalized, plan);
    return plan;
  } catch (err) {
    console.error(
      `[API:Live] Failed to fetch plan "${planId}" from live backend (${API_BASE_URL}):`,
      err
    );
    throw err;
  }
}

/**
 * POST approval or rejection for a delivery plan.
 * If isDemo is true, updates local fallback store and localStorage.
 * If isDemo is false, posts to live FastAPI backend POST /api/plans/{planId}/approval.
 */
export async function approvePlan(
  planId: string,
  request: ApprovalRequest,
  isDemo: boolean = false
): Promise<DeliveryPlan> {
  const normalized = planId.trim().toLowerCase();

  if (isDemo) {
    const current =
      localPlanStore.get(normalized) ??
      MOCK_PLANS.find((p) => p.plan_id.toLowerCase() === normalized) ??
      synthesizePlan(planId);

    const updated: DeliveryPlan = {
      ...current,
      status: request.approved ? "APPROVED" : "REJECTED",
    };
    localPlanStore.set(normalized, updated);

    if (typeof window !== "undefined") {
      try {
        localStorage.setItem(
          `reliefroute_plan_${normalized}`,
          JSON.stringify(updated)
        );
      } catch {
        // Ignore storage error
      }
    }

    return structuredClone(updated);
  }

  // Live Mode: POST /api/plans/{plan_id}/approval
  const encoded = encodeURIComponent(planId);
  const bodyPayload = JSON.stringify({
    approved: request.approved,
    approver_id: request.approver_id || "operator-01",
    comment: request.comment ?? "Operator decision",
    decided_at: request.decided_at || new Date().toISOString(),
  });

  const updated = await tryFetch<DeliveryPlan>(
    `/api/plans/${encoded}/approval`,
    `/plans/${encoded}/approval`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: bodyPayload,
    }
  );
  localPlanStore.set(normalized, updated);
  return updated;
}

/**
 * POST driver dispatch instruction for an approved plan.
 * If isDemo is true, simulates dispatch result and updates local store.
 * If isDemo is false, posts to live FastAPI backend POST /api/plans/{planId}/dispatch.
 */
export async function dispatchPlan(
  planId: string,
  request: DispatchRequest,
  isDemo: boolean = false
): Promise<DispatchResult> {
  const normalized = planId.trim().toLowerCase();

  if (isDemo) {
    const current = localPlanStore.get(normalized);
    if (current) {
      current.status = "DISPATCHED";
      localPlanStore.set(normalized, current);
      if (typeof window !== "undefined") {
        try {
          localStorage.setItem(
            `reliefroute_plan_${normalized}`,
            JSON.stringify(current)
          );
        } catch {
          // Ignore
        }
      }
    }

    return {
      dispatch_id: `dsp-${Date.now().toString(36)}`,
      plan_id: planId,
      provider_message_id: `tg-msg-${Math.floor(100000 + Math.random() * 900000)}`,
      status: "SENT",
      attempted_at: new Date().toISOString(),
    };
  }

  // Live Mode: POST /api/plans/{plan_id}/dispatch
  const encoded = encodeURIComponent(planId);
  const bodyPayload = JSON.stringify({
    driver_id: request.driver_id || "driver-default-01",
    message: request.message || `Emergency dispatch for plan ${planId}`,
    idempotency_key: request.idempotency_key || `idemp-${planId}-${Date.now()}`,
  });

  const result = await tryFetch<DispatchResult>(
    `/api/plans/${encoded}/dispatch`,
    `/plans/${encoded}/dispatch`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: bodyPayload,
    }
  );

  const current = localPlanStore.get(normalized);
  if (current) {
    current.status = "DISPATCHED";
    localPlanStore.set(normalized, current);
  }
  return result;
}

/**
 * Fetch citizen reports from the triage agent.
 * If isDemo is true, returns mock citizen reports.
 * If isDemo is false, queries live FastAPI GET /api/citizen-reports.
 */
export async function getCitizenReports(isDemo: boolean = false): Promise<CitizenReport[]> {
  if (isDemo) {
    return structuredClone(MOCK_REPORTS);
  }

  try {
    const data = await tryFetch<CitizenReport[]>("/api/citizen-reports", "/citizen-reports");
    if (Array.isArray(data)) {
      return data;
    }
    return [];
  } catch (err) {
    console.warn(
      `[API:Live] Failed to fetch citizen reports from live backend (${API_BASE_URL}):`,
      err
    );
    return [];
  }
}

/**
 * Fetch audit trail events for a plan entity.
 * Tries FastAPI backend GET /api/audit-events, falls back to synthetic timeline.
 */
export async function getAuditEvents(entityId: string): Promise<AuditEvent[]> {
  try {
    const encoded = encodeURIComponent(entityId);
    return await tryFetch<AuditEvent[]>(
      `/api/audit-events?entity_id=${encoded}`,
      `/audit-events?entity_id=${encoded}`
    );
  } catch (err) {
    console.warn(
      `[API] Failed to fetch audit events for "${entityId}" from live backend (${API_BASE_URL}), using mock fallback:`,
      err
    );

    return [
      {
        event_id: `evt-${entityId}-01`,
        occurred_at: new Date(Date.now() - 300000).toISOString(),
        actor: "reliefroute-gen-ai",
        action: "EMERGENCY_REPORT_INGESTED",
        entity_type: "CitizenReport",
        entity_id: entityId,
        outcome: "SUCCESS",
        details: { channel: "telegram", status: "VERIFIED" },
        source_refs: [],
      },
      {
        event_id: `evt-${entityId}-02`,
        occurred_at: new Date(Date.now() - 240000).toISOString(),
        actor: "reliefroute-agent",
        action: "PLAN_CREATED",
        entity_type: "DeliveryPlan",
        entity_id: entityId,
        outcome: "SUCCESS",
        details: { plan_id: entityId, priority: "HIGH" },
        source_refs: [],
      },
      {
        event_id: `evt-${entityId}-03`,
        occurred_at: new Date(Date.now() - 180000).toISOString(),
        actor: "hazard-service",
        action: "HAZARD_ZONE_MAPPED",
        entity_type: "HazardAssessment",
        entity_id: `haz-${entityId}`,
        outcome: "SUCCESS",
        details: { risk_level: "MODERATE", flood_polygons: 1 },
        source_refs: [],
      },
      {
        event_id: `evt-${entityId}-04`,
        occurred_at: new Date(Date.now() - 120000).toISOString(),
        actor: "routing-engine",
        action: "ROUTING_COMPUTED",
        entity_type: "RouteResult",
        entity_id: entityId,
        outcome: "SUCCESS",
        details: { avoids_flood_polygon: true, status: "READY_FOR_APPROVAL" },
        source_refs: [],
      },
    ];
  }
}
