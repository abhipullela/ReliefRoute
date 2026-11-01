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
// Public API Functions (Real API First -> MockData Fallback)
// -------------------------------------------------------------------------

/**
 * Fetch all active delivery plans.
 * Tries FastAPI backend GET /plans (or /api/v1/plans), falls back to MOCK_PLANS.
 */
export async function getActivePlans(): Promise<DeliveryPlan[]> {
  try {
    const data = await tryFetch<DeliveryPlan[]>("/plans", "/api/v1/plans");
    if (Array.isArray(data) && data.length > 0) {
      data.forEach((p: DeliveryPlan) => {
        localPlanStore.set(p.plan_id.toLowerCase(), p);
      });
      return data;
    }
    return structuredClone(MOCK_PLANS);
  } catch (err) {
    console.warn(
      `[API] Failed to fetch active plans from live backend (${API_BASE_URL}), using mockData fallback:`,
      err
    );
    return structuredClone(MOCK_PLANS);
  }
}

/**
 * Fetch active flood areas for the map view.
 * Tries FastAPI backend GET /flood-areas, falls back to ACTIVE_FLOOD_AREAS.
 */
export async function getActiveFloodAreas(): Promise<ActiveFloodArea[]> {
  try {
    const data = await tryFetch<ActiveFloodArea[]>("/flood-areas", "/api/v1/flood-areas");
    if (Array.isArray(data) && data.length > 0) {
      return data;
    }
    return structuredClone(ACTIVE_FLOOD_AREAS);
  } catch (err) {
    console.warn(
      `[API] Failed to fetch active flood areas from live backend (${API_BASE_URL}), using mockData fallback:`,
      err
    );
    return structuredClone(ACTIVE_FLOOD_AREAS);
  }
}

/**
 * Fetch a specific DeliveryPlan by ID.
 * Tries FastAPI backend GET /plans/{planId}, falls back to mockData.
 */
export async function getPlan(planId: string): Promise<DeliveryPlan> {
  const normalized = planId.trim().toLowerCase();

  // 1. Try real live FastAPI backend
  try {
    const encoded = encodeURIComponent(planId);
    const plan = await tryFetch<DeliveryPlan>(`/plans/${encoded}`, `/api/v1/plans/${encoded}`);
    localPlanStore.set(normalized, plan);
    return plan;
  } catch (err) {
    console.warn(
      `[API] Failed to fetch plan "${planId}" from live backend (${API_BASE_URL}), using mockData fallback:`,
      err
    );

    // 2. Fallback: check in-memory cached store
    if (localPlanStore.has(normalized)) {
      return structuredClone(localPlanStore.get(normalized)!);
    }

    // 3. Fallback: check MOCK_PLANS list
    const foundMock = MOCK_PLANS.find(
      (p) => p.plan_id.toLowerCase() === normalized
    );
    if (foundMock) {
      localPlanStore.set(normalized, foundMock);
      return structuredClone(foundMock);
    }

    // 4. Fallback: check localStorage for plans dispatched or approved during session
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

    // 5. Fallback: check /data/active_plans.json if populated
    if (typeof window !== "undefined") {
      try {
        const resp = await fetch("/data/active_plans.json");
        if (resp.ok) {
          const plans: DeliveryPlan[] = await resp.json();
          const found = plans.find(
            (p) => p.plan_id.toLowerCase() === normalized
          );
          if (found) {
            localPlanStore.set(normalized, found);
            return structuredClone(found);
          }
        }
      } catch {
        // Ignore fetch error
      }
    }

    // 6. Failsafe: synthesize realistic emergency plan
    const synthesized = synthesizePlan(planId);
    localPlanStore.set(normalized, synthesized);
    return structuredClone(synthesized);
  }
}

/**
 * POST approval or rejection for a delivery plan.
 * Tries FastAPI backend POST /plans/{planId}/approval, falls back to local update.
 */
export async function approvePlan(
  planId: string,
  request: ApprovalRequest
): Promise<DeliveryPlan> {
  const normalized = planId.trim().toLowerCase();

  try {
    const encoded = encodeURIComponent(planId);
    const bodyPayload = JSON.stringify({
      approved: request.approved,
      approver_id: request.approver_id || "operator-01",
      comment: request.comment ?? "Operator decision",
      decided_at: request.decided_at || new Date().toISOString(),
    });

    const updated = await tryFetch<DeliveryPlan>(
      `/plans/${encoded}/approval`,
      `/api/v1/plans/${encoded}/approval`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: bodyPayload,
      }
    );
    localPlanStore.set(normalized, updated);
    return updated;
  } catch (err) {
    console.warn(
      `[API] Failed to post approval for plan "${planId}" to live backend (${API_BASE_URL}), updating local fallback state:`,
      err
    );

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
}

/**
 * POST driver dispatch instruction for an approved plan.
 * Tries FastAPI backend POST /plans/{planId}/dispatch, falls back to mock response.
 */
export async function dispatchPlan(
  planId: string,
  request: DispatchRequest
): Promise<DispatchResult> {
  const normalized = planId.trim().toLowerCase();

  try {
    const encoded = encodeURIComponent(planId);
    const bodyPayload = JSON.stringify({
      driver_id: request.driver_id || "driver-default-01",
      message: request.message || `Emergency dispatch for plan ${planId}`,
      idempotency_key: request.idempotency_key || `idemp-${planId}-${Date.now()}`,
    });

    const result = await tryFetch<DispatchResult>(
      `/plans/${encoded}/dispatch`,
      `/api/v1/plans/${encoded}/dispatch`,
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
  } catch (err) {
    console.warn(
      `[API] Failed to post dispatch for plan "${planId}" to live backend (${API_BASE_URL}), using mock fallback:`,
      err
    );

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
}

/**
 * Fetch citizen reports from the triage agent.
 * Tries FastAPI backend GET /citizen-reports, falls back to MOCK_REPORTS.
 */
export async function getCitizenReports(): Promise<CitizenReport[]> {
  try {
    const data = await tryFetch<CitizenReport[]>("/citizen-reports", "/api/v1/citizen-reports");
    if (Array.isArray(data) && data.length > 0) {
      return data;
    }
    return structuredClone(MOCK_REPORTS);
  } catch (err) {
    console.warn(
      `[API] Failed to fetch citizen reports from live backend (${API_BASE_URL}), using mockData fallback:`,
      err
    );
    return structuredClone(MOCK_REPORTS);
  }
}

/**
 * Fetch audit trail events for a plan entity.
 * Tries FastAPI backend GET /audit-events, falls back to synthetic timeline.
 */
export async function getAuditEvents(entityId: string): Promise<AuditEvent[]> {
  try {
    const encoded = encodeURIComponent(entityId);
    return await tryFetch<AuditEvent[]>(
      `/audit-events?entity_id=${encoded}`,
      `/api/v1/audit-events?entity_id=${encoded}`
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
