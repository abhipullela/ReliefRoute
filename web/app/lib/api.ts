// app/lib/api.ts
// Thin typed fetch wrapper that enforces the /api/v1 contract.
// Rules:
//   - All errors are thrown as ApiError instances; callers decide how to present them.
//   - 409 Conflict: idempotency — do NOT retry.
//   - 502/503/504: upstream degraded — surface prominently in UI.
//   - No DB calls, no Prisma, no SQL. This file ONLY calls /api/v1/*.

import type {
  DeliveryPlan,
  ApprovalRequest,
  DispatchRequest,
  DispatchResult,
  AuditEvent,
  ApiErrorResponse,
} from "@/app/types/api";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

// -------------------------------------------------------------------------
// Custom error
// -------------------------------------------------------------------------

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly isConflict: boolean;
  readonly isDegraded: boolean; // 502/503/504

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
// Core fetch helper
// -------------------------------------------------------------------------

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;

  let resp: Response;
  try {
    resp = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...(options?.headers ?? {}),
      },
    });
  } catch (err) {
    // Network-level error (DNS, refused connection, etc.)
    throw new ApiError(503, {
      code: "UPSTREAM_UNAVAILABLE",
      message: "Cannot reach ReliefRoute API. Is the backend running?",
      retryable: true,
    });
  }

  if (!resp.ok) {
    let body: ApiErrorResponse = {
      code: "INTERNAL_ERROR",
      message: `HTTP ${resp.status}`,
      retryable: false,
    };
    try {
      body = await resp.json();
    } catch {
      // Non-JSON error body — keep default
    }
    throw new ApiError(resp.status, body);
  }

  if (resp.status === 204) return undefined as unknown as T;
  return resp.json() as Promise<T>;
}

// -------------------------------------------------------------------------
// Mock data for test plan ID
// -------------------------------------------------------------------------

const MOCK_TEST_PLAN: DeliveryPlan = {
  plan_id: "test",
  created_at: new Date().toISOString(),
  supplier_id: "supplier-electronic-city-01",
  commodity: "Emergency Medical Kits & Water Purification Packs",
  quantity: 450,
  unit: "crates",
  origin: {
    latitude: 12.8442,
    longitude: 77.6648,
  },
  destination: {
    latitude: 12.7112,
    longitude: 77.6954,
  },
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
        [77.6648, 12.8442], // Electronic City Phase 1
        [77.6715, 12.836],  // Elevated tollway junction
        [77.678, 12.825],   // Hebbagodi
        [77.686, 12.812],   // Bommasandra Industrial Area
        [77.694, 12.798],   // Chandapura Circle
        [77.698, 12.775],   // Suragajakkanahalli
        [77.701, 12.752],   // Marsur
        [77.7025, 12.731],  // Karpur / Anekal Road
        [77.6954, 12.7112], // Anekal Relief Center
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
};

let mockPlanState: DeliveryPlan | null = null;

// -------------------------------------------------------------------------
// Public API functions
// -------------------------------------------------------------------------

/** Fetch the full DeliveryPlan including route and hazard assessment ID. */
export async function getPlan(planId: string): Promise<DeliveryPlan> {
  if (planId.toLowerCase() === "test") {
    return structuredClone(mockPlanState ?? MOCK_TEST_PLAN);
  }
  return apiFetch<DeliveryPlan>(`/api/v1/plans/${planId}`);
}

/**
 * POST an approval or rejection decision for a plan.
 * Returns the updated plan. Throws ApiError on 409 (already decided).
 */
export async function approvePlan(
  planId: string,
  request: ApprovalRequest
): Promise<DeliveryPlan> {
  if (planId.toLowerCase() === "test") {
    mockPlanState = {
      ...(mockPlanState ?? MOCK_TEST_PLAN),
      status: request.approved ? "APPROVED" : "REJECTED",
    };
    return structuredClone(mockPlanState);
  }
  return apiFetch<DeliveryPlan>(`/api/v1/plans/${planId}/approval`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

/**
 * POST a dispatch instruction for an approved plan.
 * Returns DispatchResult. Throws ApiError on 409 (already dispatched).
 */
export async function dispatchPlan(
  planId: string,
  request: DispatchRequest
): Promise<DispatchResult> {
  if (planId.toLowerCase() === "test") {
    mockPlanState = {
      ...(mockPlanState ?? MOCK_TEST_PLAN),
      status: "DISPATCHED",
    };
    return {
      dispatch_id: `mock-dispatch-${Date.now()}`,
      plan_id: "test",
      provider_message_id: "tg-msg-789102",
      status: "SENT",
      attempted_at: new Date().toISOString(),
    };
  }
  return apiFetch<DispatchResult>(`/api/v1/plans/${planId}/dispatch`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

/**
 * Fetch audit events for a specific entity (plan).
 * Returns events in ascending chronological order.
 */
export async function getAuditEvents(entityId: string): Promise<AuditEvent[]> {
  if (entityId.toLowerCase() === "test") {
    return [
      {
        event_id: "evt-test-01",
        occurred_at: new Date(Date.now() - 180000).toISOString(),
        actor: "reliefroute-agent",
        action: "PLAN_CREATED",
        entity_type: "DeliveryPlan",
        entity_id: "test",
        outcome: "SUCCESS",
        details: { commodity: "Medical Kits", quantity: 450, unit: "crates" },
        source_refs: [],
      },
      {
        event_id: "evt-test-02",
        occurred_at: new Date(Date.now() - 120000).toISOString(),
        actor: "hazard-service",
        action: "HAZARD_ZONE_MAPPED",
        entity_type: "HazardAssessment",
        entity_id: "haz-assess-flood-test",
        outcome: "SUCCESS",
        details: { risk_level: "MODERATE", polygons_detected: 1 },
        source_refs: [],
      },
      {
        event_id: "evt-test-03",
        occurred_at: new Date(Date.now() - 60000).toISOString(),
        actor: "reliefroute-agent",
        action: "ROUTING_COMPUTED",
        entity_type: "RouteResult",
        entity_id: "test",
        outcome: "SUCCESS",
        details: { distance_km: 18.5, avoids_hazard: true },
        source_refs: [],
      },
    ];
  }
  return apiFetch<AuditEvent[]>(
    `/api/v1/audit-events?entity_id=${encodeURIComponent(entityId)}`
  );
}
