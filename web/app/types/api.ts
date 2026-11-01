// app/types/api.ts
// Mirror of shared/models.py — strictly typed for the TypeScript frontend.
// Source of truth is the Python models; update here when Python contracts change.

export interface LatLon {
  latitude: number;
  longitude: number;
}

export interface GeoJSONPolygon {
  type: "Polygon";
  coordinates: number[][][]; // [longitude, latitude] per GeoJSON spec
}

export interface SourceRef {
  provider: string;
  url?: string | null;
  retrieved_at: string; // ISO-8601
  observed_at?: string | null;
  stale: boolean;
  notes?: string | null;
}

export interface ServiceError {
  code: string;
  message: string;
  retryable: boolean;
  provider?: string | null;
  details: Record<string, unknown>;
  occurred_at: string;
}

export interface RouteResult {
  provider: string;
  geometry?: Record<string, unknown> | null; // GeoJSON LineString
  distance_m: number;
  duration_s: number;
  avoids_requested_polygons: boolean;
  risk_level: "LOW" | "MODERATE" | "HIGH" | "UNKNOWN";
  warnings: string[];
  source: SourceRef;
}

export interface HazardAssessment {
  assessment_id: string;
  generated_at: string;
  risk_level: "LOW" | "MODERATE" | "HIGH" | "UNKNOWN";
  polygons: GeoJSONPolygon[];
  sources: SourceRef[];
  rationale: string[];
  limitations: string[];
}

export type PlanStatus =
  | "DRAFT"
  | "NEEDS_APPROVAL"
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "DISPATCHED"
  | "ACKNOWLEDGED"
  | "IN_TRANSIT"
  | "COMPLETED"
  | "FAILED"
  | "REPLAN_REQUIRED";

export interface DeliveryPlan {
  plan_id: string;
  created_at: string;
  supplier_id: string;
  commodity: string;
  quantity: number;
  unit: string;
  origin: LatLon;
  destination: LatLon;
  route?: RouteResult | null;
  hazard_assessment_id: string;
  status: PlanStatus;
  approval_required: boolean;
  idempotency_key: string;
  rationale: string[];
  source_refs: SourceRef[];
  hazard_polygons?: GeoJSONPolygon[];
  gen_ai_extraction?: GenAIExtractedData;
}

export interface GenAIExtractedData {
  emergency_type: string;
  requested_supplies: string[];
  extracted_location: string;
  original_message?: string;
  confidence?: number;
  people_affected?: number;
}

export interface ActiveFloodArea {
  plan_id: string;
  name: string;
  coordinates: [number, number]; // [longitude, latitude]
  severity: "CRITICAL" | "HIGH" | "MODERATE";
  water_level: string;
  commodity: string;
  status: PlanStatus;
  people_affected: number;
}

export interface ApprovalRequest {
  plan_id: string;
  approved: boolean;
  approver_id: string;
  comment?: string | null;
  decided_at: string;
}

export interface DispatchRequest {
  plan_id: string;
  driver_id: string;
  message: string;
  idempotency_key: string;
}

export interface DispatchResult {
  dispatch_id: string;
  plan_id: string;
  provider_message_id?: string | null;
  status: "SENT" | "FAILED";
  attempted_at: string;
  error?: ServiceError | null;
}

export interface AuditEvent {
  event_id: string;
  occurred_at: string;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string;
  outcome: string;
  details: Record<string, unknown>;
  source_refs: SourceRef[];
}

// API error response shape from the FastAPI backend
export interface ApiErrorResponse {
  code: string;
  message: string;
  retryable: boolean;
  provider?: string | null;
  details?: Record<string, unknown>;
  correlation_id?: string;
}
