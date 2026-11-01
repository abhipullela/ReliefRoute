// app/lib/mockData.ts
// Single source of mock data for all ReliefRoute portal views.
// Covers the full demo flow: Citizen Report → AI Intelligence → Plan → Approval → Dispatch → Audit.

import type {
  DeliveryPlan,
  ActiveFloodArea,
} from "@/app/types/api";

// ─────────────────────────────────────────────────────────────────────────────
// Supplemental types (for pages not yet covered by api.ts)
// ─────────────────────────────────────────────────────────────────────────────

export type EmergencyType =
  | "FLOOD"
  | "EARTHQUAKE"
  | "CYCLONE"
  | "FIRE"
  | "DROUGHT"
  | "LANDSLIDE"
  | "MEDICAL";

export type ReportStatus =
  | "RECEIVED"
  | "AI_PROCESSING"
  | "VERIFIED"
  | "PLAN_GENERATED"
  | "APPROVED"
  | "DISPATCHED"
  | "DELIVERED";

export interface CitizenReport {
  report_id: string;
  submitted_at: string;
  emergency_type: EmergencyType;
  description: string;
  location: string;
  coordinates: { lat: number; lng: number };
  people_affected: number;
  required_assistance: string[];
  status: ReportStatus;
  anonymous: boolean;
  telegram_user_id?: string;
  image_urls?: string[];
  ai_confidence?: number;
}

export interface AIExtraction {
  report_id: string;
  original_message: string;
  identified_type: EmergencyType;
  extracted_location: string;
  commodities: { item: string; quantity: number; unit: string }[];
  ai_confidence: number; // 0-100
  missing_info: string[];
  processed_at: string;
}

export interface Supplier {
  supplier_id: string;
  name: string;
  location: string;
  coordinates: { lat: number; lng: number };
  inventory: { item: string; quantity: number; unit: string; available: boolean }[];
  contact: string;
  active: boolean;
}

export interface DistributionCentre {
  centre_id: string;
  name: string;
  location: string;
  coordinates: { lat: number; lng: number };
  capacity: number;
  current_load: number;
}

export interface Vehicle {
  vehicle_id: string;
  driver_name: string;
  driver_phone: string;
  plate: string;
  type: "TRUCK" | "VAN" | "BOAT" | "HELICOPTER";
  status: "AVAILABLE" | "EN_ROUTE" | "DELIVERED" | "MAINTENANCE";
  coordinates?: { lat: number; lng: number };
}

export interface DispatchRecord {
  dispatch_id: string;
  plan_id: string;
  driver_name: string;
  vehicle_plate: string;
  vehicle_type: string;
  origin: string;
  destination: string;
  commodity: string;
  quantity: number;
  unit: string;
  status: "SENT" | "ACKNOWLEDGED" | "EN_ROUTE" | "DELIVERED" | "FAILED";
  dispatched_at: string;
  eta: string;
  telegram_message_id?: string;
}

export interface MapMarker {
  id: string;
  type: "REPORT" | "SUPPLIER" | "CENTRE" | "VEHICLE" | "BLOCKED";
  coordinates: [number, number]; // [lng, lat]
  label: string;
  plan_id?: string;
  report_id?: string;
  risk_level?: "LOW" | "MODERATE" | "HIGH";
}

export interface AuditTimeline {
  event_id: string;
  occurred_at: string;
  actor: string;
  action: string;
  description: string;
  entity_id: string;
  entity_type: string;
  outcome: "SUCCESS" | "FAILURE" | "PENDING";
  icon_type: "report" | "ai" | "verify" | "plan" | "approve" | "dispatch" | "delivered";
}

// ─────────────────────────────────────────────────────────────────────────────
// Citizen Reports
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_REPORTS: CitizenReport[] = [
  {
    report_id: "RPT-001",
    submitted_at: new Date(Date.now() - 5 * 3600000).toISOString(),
    emergency_type: "FLOOD",
    description:
      "Roads near Chandapura Circle are completely submerged. At least 200 families stuck on rooftops. We need water, food, and rescue boats immediately.",
    location: "Chandapura Circle, Bengaluru",
    coordinates: { lat: 12.798, lng: 77.694 },
    people_affected: 850,
    required_assistance: ["Water", "Food", "Rescue", "Medical"],
    status: "DISPATCHED",
    anonymous: false,
    telegram_user_id: "tg_user_412",
    ai_confidence: 94,
  },
  {
    report_id: "RPT-002",
    submitted_at: new Date(Date.now() - 3 * 3600000).toISOString(),
    emergency_type: "FLOOD",
    description:
      "Marsur village cut off. Entire ground floor of 40 houses flooded. Need clothes and blankets for children.",
    location: "Marsur, Anekal Taluk",
    coordinates: { lat: 12.752, lng: 77.701 },
    people_affected: 340,
    required_assistance: ["Clothing", "Shelter", "Food"],
    status: "PLAN_GENERATED",
    anonymous: true,
    ai_confidence: 87,
  },
  {
    report_id: "RPT-003",
    submitted_at: new Date(Date.now() - 1.5 * 3600000).toISOString(),
    emergency_type: "MEDICAL",
    description:
      "Three elderly residents with chronic conditions unable to access medications. One showing signs of diabetic emergency.",
    location: "Suragajakkanahalli, Bengaluru",
    coordinates: { lat: 12.775, lng: 77.698 },
    people_affected: 12,
    required_assistance: ["Medical"],
    status: "VERIFIED",
    anonymous: false,
    telegram_user_id: "tg_user_789",
    ai_confidence: 92,
  },
  {
    report_id: "RPT-004",
    submitted_at: new Date(Date.now() - 45 * 60000).toISOString(),
    emergency_type: "FLOOD",
    description:
      "Newly reported: Karpur road bridge cracked, vehicles unable to pass. Many people stranded.",
    location: "Karpur, Anekal Road",
    coordinates: { lat: 12.731, lng: 77.7025 },
    people_affected: 520,
    required_assistance: ["Rescue", "Food", "Water"],
    status: "AI_PROCESSING",
    anonymous: false,
    telegram_user_id: "tg_user_1023",
    ai_confidence: 79,
  },
  {
    report_id: "RPT-005",
    submitted_at: new Date(Date.now() - 10 * 60000).toISOString(),
    emergency_type: "EARTHQUAKE",
    description:
      "Tremors felt in Hosur area. Multiple building walls cracked. Need structural assessment and emergency shelter.",
    location: "Hosur, Tamil Nadu border",
    coordinates: { lat: 12.74, lng: 77.83 },
    people_affected: 200,
    required_assistance: ["Shelter", "Medical", "Food"],
    status: "RECEIVED",
    anonymous: true,
    ai_confidence: 68,
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// AI Extractions
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_AI_EXTRACTIONS: AIExtraction[] = [
  {
    report_id: "RPT-001",
    original_message:
      "Roads near Chandapura Circle are completely submerged. At least 200 families stuck on rooftops. We need water, food, and rescue boats immediately.",
    identified_type: "FLOOD",
    extracted_location: "Chandapura Circle, Bengaluru (12.798°N, 77.694°E)",
    commodities: [
      { item: "Drinking Water (5L bottles)", quantity: 4000, unit: "bottles" },
      { item: "Ready-to-eat Meal Packs", quantity: 2500, unit: "packets" },
      { item: "Inflatable Rescue Boats", quantity: 8, unit: "units" },
      { item: "Emergency Medical Kits", quantity: 50, unit: "kits" },
    ],
    ai_confidence: 94,
    missing_info: ["Exact street name", "Available landing zone for boats"],
    processed_at: new Date(Date.now() - 4.8 * 3600000).toISOString(),
  },
  {
    report_id: "RPT-002",
    original_message:
      "Marsur village cut off. Entire ground floor of 40 houses flooded. Need clothes and blankets for children.",
    identified_type: "FLOOD",
    extracted_location: "Marsur, Anekal Taluk (12.752°N, 77.701°E)",
    commodities: [
      { item: "Children Clothing Bundles", quantity: 300, unit: "bundles" },
      { item: "Thermal Blankets", quantity: 500, unit: "units" },
      { item: "Food Packets", quantity: 1200, unit: "packets" },
    ],
    ai_confidence: 87,
    missing_info: ["Age distribution of children", "Current water level depth"],
    processed_at: new Date(Date.now() - 2.8 * 3600000).toISOString(),
  },
  {
    report_id: "RPT-003",
    original_message:
      "Three elderly residents with chronic conditions unable to access medications. One showing signs of diabetic emergency.",
    identified_type: "MEDICAL",
    extracted_location: "Suragajakkanahalli, Bengaluru (12.775°N, 77.698°E)",
    commodities: [
      { item: "Insulin & Diabetes Medication", quantity: 30, unit: "units" },
      { item: "Blood Glucose Test Kits", quantity: 10, unit: "kits" },
      { item: "Emergency Medical Kits", quantity: 5, unit: "kits" },
    ],
    ai_confidence: 92,
    missing_info: ["Specific medication names", "Patient allergy info"],
    processed_at: new Date(Date.now() - 1.3 * 3600000).toISOString(),
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Delivery Plans
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_PLANS: DeliveryPlan[] = [
  {
    plan_id: "PLAN-2024-001",
    created_at: new Date(Date.now() - 4 * 3600000).toISOString(),
    supplier_id: "supplier-electronic-city-01",
    commodity: "Drinking Water & Emergency Meal Packs",
    quantity: 450,
    unit: "crates",
    origin: { latitude: 12.8442, longitude: 77.6648 },
    destination: { latitude: 12.798, longitude: 77.694 },
    status: "DISPATCHED",
    approval_required: true,
    idempotency_key: "idemp-plan-001",
    hazard_assessment_id: "haz-001",
    rationale: [
      "Heavy precipitation (>45mm/hr) detected along Chandapura basin.",
      "Rerouted via Hosur Rd primary arterial to circumvent flood polygon.",
      "850 people affected — high priority dispatch authorized.",
    ],
    source_refs: [
      { provider: "Open-Meteo & CWC", url: "https://api.open-meteo.com", retrieved_at: new Date().toISOString(), stale: false, notes: "Modeled flood risk" },
    ],
    route: {
      provider: "openrouteservice",
      geometry: { type: "LineString", coordinates: [[77.6648, 12.8442],[77.678, 12.825],[77.686, 12.812],[77.694, 12.798]] },
      distance_m: 12800, duration_s: 1350, avoids_requested_polygons: true, risk_level: "MODERATE",
      warnings: ["Surface runoff advisory active near Chandapura basin"],
      source: { provider: "openrouteservice", retrieved_at: new Date().toISOString(), stale: false },
    },
    hazard_polygons: [{ type: "Polygon", coordinates: [[[77.682,12.805],[77.712,12.805],[77.718,12.775],[77.688,12.77],[77.682,12.805]]] }],
    gen_ai_extraction: {
      emergency_type: "FLASH FLOOD INUNDATION",
      requested_supplies: ["Drinking Water (5L)", "Emergency Meal Packs"],
      extracted_location: "Chandapura Circle Basin (Electronic City Sector)",
      original_message: "Heavy flash flood at Chandapura circle, water is at 1.5 meters! 850 people isolated, need water and food packs urgently.",
      confidence: 96.8,
      people_affected: 850,
    },
  },
  {
    plan_id: "PLAN-2024-002",
    created_at: new Date(Date.now() - 2.5 * 3600000).toISOString(),
    supplier_id: "supplier-bommasandra-02",
    commodity: "Clothing & Thermal Blankets",
    quantity: 800,
    unit: "bundles",
    origin: { latitude: 12.836, longitude: 77.6715 },
    destination: { latitude: 12.752, longitude: 77.701 },
    status: "PENDING_APPROVAL",
    approval_required: true,
    idempotency_key: "idemp-plan-002",
    hazard_assessment_id: "haz-002",
    rationale: [
      "Marsur village isolated — ground routes partially compromised.",
      "340 people need clothing and shelter materials urgently.",
      "Human approval required: route passes within 2km of hazard zone.",
    ],
    source_refs: [],
    route: {
      provider: "openrouteservice",
      geometry: { type: "LineString", coordinates: [[77.6715,12.836],[77.686,12.812],[77.698,12.775],[77.701,12.752]] },
      distance_m: 10200, duration_s: 1140, avoids_requested_polygons: false, risk_level: "HIGH",
      warnings: ["Route passes near active flood zone", "Bridge condition at Marsur Road unverified"],
      source: { provider: "openrouteservice", retrieved_at: new Date().toISOString(), stale: false },
    },
    hazard_polygons: [{ type: "Polygon", coordinates: [[[77.685,12.785],[77.715,12.785],[77.72,12.765],[77.69,12.76],[77.685,12.785]]] }],
    gen_ai_extraction: {
      emergency_type: "VILLAGE ISOLATION & FLOODING",
      requested_supplies: ["Thermal Blankets", "Clothing Bundles"],
      extracted_location: "Marsur Village Centre (Anekal)",
      original_message: "Marsur village completely isolated, lake overflowed, houses submerged. 340 people cold and wet, please send blankets and clothing.",
      confidence: 95.2,
      people_affected: 340,
    },
  },
  {
    plan_id: "PLAN-2024-003",
    created_at: new Date(Date.now() - 1 * 3600000).toISOString(),
    supplier_id: "supplier-hosur-medical-03",
    commodity: "Insulin & Medical Emergency Kits",
    quantity: 45,
    unit: "kits",
    origin: { latitude: 12.74, longitude: 77.83 },
    destination: { latitude: 12.775, longitude: 77.698 },
    status: "NEEDS_APPROVAL",
    approval_required: true,
    idempotency_key: "idemp-plan-003",
    hazard_assessment_id: "haz-003",
    rationale: [
      "Medical emergency — diabetic patient identified in report.",
      "Time-critical delivery, fastest route selected despite moderate risk.",
      "Requires immediate approval to avoid medical deterioration.",
    ],
    source_refs: [],
    route: {
      provider: "openrouteservice",
      geometry: { type: "LineString", coordinates: [[77.83,12.74],[77.78,12.755],[77.73,12.768],[77.698,12.775]] },
      distance_m: 15600, duration_s: 1800, avoids_requested_polygons: true, risk_level: "MODERATE",
      warnings: ["Rain-slicked roads on Hosur highway stretch"],
      source: { provider: "openrouteservice", retrieved_at: new Date().toISOString(), stale: false },
    },
    hazard_polygons: [{ type: "Polygon", coordinates: [[[77.685,12.785],[77.715,12.785],[77.72,12.765],[77.69,12.76],[77.685,12.785]]] }],
    gen_ai_extraction: {
      emergency_type: "CRITICAL MEDICAL EMERGENCY",
      requested_supplies: ["Insulin (Rapid Acting)", "Emergency Medical Trauma Kits"],
      extracted_location: "Anekal South Relief Sector",
      original_message: "Diabetic patient suffering acute emergency at Anekal South relief sector, need rapid-acting insulin and sterile medical kits immediately!",
      confidence: 98.4,
      people_affected: 120,
    },
  },
  {
    plan_id: "PLAN-2024-004",
    created_at: new Date(Date.now() - 45 * 60000).toISOString(),
    supplier_id: "supplier-electronic-city-01",
    commodity: "Water Purification Tablets & Dry Rations",
    quantity: 300,
    unit: "packs",
    origin: { latitude: 12.8442, longitude: 77.6648 },
    destination: { latitude: 12.822, longitude: 77.728 },
    status: "NEEDS_APPROVAL",
    approval_required: true,
    idempotency_key: "idemp-plan-004",
    hazard_assessment_id: "haz-004",
    rationale: [
      "Muthanallur Lake breached drainage culverts, overflowing southern bypass.",
      "260 residents in low-lying settlement isolated by 0.9m flash flood waters.",
      "Rerouted via northern service road to circumvent submerged causeway.",
    ],
    source_refs: [
      { provider: "Open-Meteo & CWC", url: "https://api.open-meteo.com", retrieved_at: new Date().toISOString(), stale: false, notes: "Modeled flood risk" },
    ],
    route: {
      provider: "openrouteservice",
      geometry: { type: "LineString", coordinates: [[77.6648,12.8442],[77.685,12.835],[77.705,12.828],[77.728,12.822]] },
      distance_m: 9400, duration_s: 1100, avoids_requested_polygons: true, risk_level: "MODERATE",
      warnings: ["High water volume across lake drainage culvert"],
      source: { provider: "openrouteservice", retrieved_at: new Date().toISOString(), stale: false },
    },
    hazard_polygons: [{ type: "Polygon", coordinates: [[[77.715,12.835],[77.745,12.835],[77.75,12.81],[77.718,12.81],[77.715,12.835]]] }],
    gen_ai_extraction: {
      emergency_type: "FLASH FLOOD RUNOFF",
      requested_supplies: ["Water Purification Tablets", "Dry Ration Packs"],
      extracted_location: "Muthanallur Lake Basin",
      original_message: "Muthanallur drainage culvert overflowed, low-lying settlement cut off. 260 residents need clean water purification tablets and rations.",
      confidence: 94.7,
      people_affected: 260,
    },
  },
  {
    plan_id: "PLAN-2024-005",
    created_at: new Date(Date.now() - 20 * 60000).toISOString(),
    supplier_id: "supplier-bommasandra-02",
    commodity: "Emergency Inflatable Rafts & Clean Water",
    quantity: 150,
    unit: "units",
    origin: { latitude: 12.836, longitude: 77.6715 },
    destination: { latitude: 12.86, longitude: 77.785 },
    status: "NEEDS_APPROVAL",
    approval_required: true,
    idempotency_key: "idemp-plan-005",
    hazard_assessment_id: "haz-005",
    rationale: [
      "Sarjapur lowland wetlands experiencing 1.8m rising storm water surge.",
      "490 citizens seeking high ground; immediate evacuation assistance requested.",
      "Severe modeled forecast risk along main arterial corridor.",
    ],
    source_refs: [
      { provider: "Open-Meteo & CWC", url: "https://api.open-meteo.com", retrieved_at: new Date().toISOString(), stale: false, notes: "Modeled flood risk" },
    ],
    route: {
      provider: "openrouteservice",
      geometry: { type: "LineString", coordinates: [[77.6715,12.836],[77.71,12.845],[77.75,12.852],[77.785,12.86]] },
      distance_m: 14200, duration_s: 1650, avoids_requested_polygons: true, risk_level: "HIGH",
      warnings: ["Submerged road sections reported along Sarjapur approach"],
      source: { provider: "openrouteservice", retrieved_at: new Date().toISOString(), stale: false },
    },
    hazard_polygons: [{ type: "Polygon", coordinates: [[[77.77,12.875],[77.805,12.875],[77.81,12.845],[77.765,12.845],[77.77,12.875]]] }],
    gen_ai_extraction: {
      emergency_type: "WETLAND SURGE & EVACUATION",
      requested_supplies: ["Inflatable Rescue Rafts", "Clean Drinking Water"],
      extracted_location: "Sarjapur Lowland Wetlands",
      original_message: "1.8m rising storm water in Sarjapur, 490 residents trapped on high ground. Send rescue rafts and clean water immediately.",
      confidence: 97.1,
      people_affected: 490,
    },
  },
];

export const ACTIVE_FLOOD_AREAS: ActiveFloodArea[] = [
  {
    plan_id: "PLAN-2024-001",
    name: "Chandapura Basin Flood Zone",
    coordinates: [77.694, 12.798],
    severity: "HIGH",
    water_level: "1.4m surge",
    commodity: "Drinking Water & Meal Packs",
    status: "DISPATCHED",
    people_affected: 850,
  },
  {
    plan_id: "PLAN-2024-002",
    name: "Marsur Village Inundation",
    coordinates: [77.701, 12.752],
    severity: "CRITICAL",
    water_level: "2.1m water level",
    commodity: "Clothing & Thermal Blankets",
    status: "PENDING_APPROVAL",
    people_affected: 340,
  },
  {
    plan_id: "PLAN-2024-003",
    name: "Anekal South Relief Sector",
    coordinates: [77.698, 12.775],
    severity: "HIGH",
    water_level: "Flash flood runoff",
    commodity: "Insulin & Medical Kits",
    status: "NEEDS_APPROVAL",
    people_affected: 120,
  },
  {
    plan_id: "PLAN-2024-004",
    name: "Muthanallur Lake Overflow",
    coordinates: [77.728, 12.822],
    severity: "MODERATE",
    water_level: "0.9m flash flood",
    commodity: "Water Purification & Rations",
    status: "NEEDS_APPROVAL",
    people_affected: 260,
  },
  {
    plan_id: "PLAN-2024-005",
    name: "Sarjapur Lowland Inundation",
    coordinates: [77.785, 12.86],
    severity: "CRITICAL",
    water_level: "1.8m rising water",
    commodity: "Emergency Rafts & Clean Water",
    status: "NEEDS_APPROVAL",
    people_affected: 490,
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Dispatch Records
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_DISPATCHES: DispatchRecord[] = [
  {
    dispatch_id: "DSP-001", plan_id: "PLAN-2024-001",
    driver_name: "Rajan Kumar", vehicle_plate: "KA 51 AB 1234", vehicle_type: "Heavy Truck",
    origin: "Electronic City Warehouse", destination: "Chandapura Circle Relief Point",
    commodity: "Drinking Water & Meal Packs", quantity: 450, unit: "crates",
    status: "EN_ROUTE",
    dispatched_at: new Date(Date.now() - 2 * 3600000).toISOString(),
    eta: new Date(Date.now() + 45 * 60000).toISOString(),
    telegram_message_id: "tg-msg-10291",
  },
  {
    dispatch_id: "DSP-002", plan_id: "PLAN-2024-002",
    driver_name: "Suresh Nair", vehicle_plate: "KA 05 TN 7890", vehicle_type: "Medium Van",
    origin: "Bommasandra Logistics Hub", destination: "Marsur Village Centre",
    commodity: "Clothing & Thermal Blankets", quantity: 800, unit: "bundles",
    status: "ACKNOWLEDGED",
    dispatched_at: new Date(Date.now() - 30 * 60000).toISOString(),
    eta: new Date(Date.now() + 90 * 60000).toISOString(),
    telegram_message_id: "tg-msg-10298",
  },
  {
    dispatch_id: "DSP-000", plan_id: "PLAN-2023-099",
    driver_name: "Priya Menon", vehicle_plate: "TN 10 CF 5566", vehicle_type: "Heavy Truck",
    origin: "Hosur Medical Depot", destination: "Anekal Relief Centre",
    commodity: "Medical Kits & Water Purification", quantity: 320, unit: "crates",
    status: "DELIVERED",
    dispatched_at: new Date(Date.now() - 6 * 3600000).toISOString(),
    eta: new Date(Date.now() - 3 * 3600000).toISOString(),
    telegram_message_id: "tg-msg-10201",
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Suppliers
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_SUPPLIERS: Supplier[] = [
  {
    supplier_id: "supplier-electronic-city-01",
    name: "Electronic City Emergency Depot",
    location: "Electronic City Phase 1, Bengaluru",
    coordinates: { lat: 12.8442, lng: 77.6648 },
    contact: "+91 80 2234 5678", active: true,
    inventory: [
      { item: "Drinking Water (5L)", quantity: 12000, unit: "bottles", available: true },
      { item: "Ready-to-eat Meals", quantity: 8500, unit: "packets", available: true },
      { item: "Medical Kits", quantity: 340, unit: "kits", available: true },
      { item: "Thermal Blankets", quantity: 2200, unit: "units", available: true },
      { item: "Rescue Boats (Inflatable)", quantity: 15, unit: "units", available: false },
    ],
  },
  {
    supplier_id: "supplier-bommasandra-02",
    name: "Bommasandra Logistics Hub",
    location: "Bommasandra Industrial Area, Bengaluru",
    coordinates: { lat: 12.836, lng: 77.6715 },
    contact: "+91 80 6677 8899", active: true,
    inventory: [
      { item: "Clothing Bundles (Mixed)", quantity: 3400, unit: "bundles", available: true },
      { item: "Thermal Blankets", quantity: 5000, unit: "units", available: true },
      { item: "Tarpaulins", quantity: 800, unit: "units", available: true },
      { item: "Dry Ration Packs", quantity: 6000, unit: "packets", available: true },
    ],
  },
  {
    supplier_id: "supplier-hosur-medical-03",
    name: "Hosur District Medical Store",
    location: "Hosur, Tamil Nadu",
    coordinates: { lat: 12.74, lng: 77.83 },
    contact: "+91 4344 233456", active: true,
    inventory: [
      { item: "Insulin (rapid-acting)", quantity: 500, unit: "vials", available: true },
      { item: "Emergency Medical Kits", quantity: 180, unit: "kits", available: true },
      { item: "ORS Packets", quantity: 10000, unit: "packets", available: true },
      { item: "Blood Glucose Test Kits", quantity: 300, unit: "kits", available: true },
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Distribution Centres
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_CENTRES: DistributionCentre[] = [
  { centre_id: "DC-001", name: "Anekal Relief Centre", location: "Anekal, Bengaluru Urban", coordinates: { lat: 12.7112, lng: 77.6954 }, capacity: 2000, current_load: 1340 },
  { centre_id: "DC-002", name: "Chandapura Emergency Hub", location: "Chandapura, Bengaluru", coordinates: { lat: 12.798, lng: 77.694 }, capacity: 800, current_load: 620 },
  { centre_id: "DC-003", name: "Hebbagodi Secondary Depot", location: "Hebbagodi, Bengaluru", coordinates: { lat: 12.825, lng: 77.678 }, capacity: 1200, current_load: 200 },
];

// ─────────────────────────────────────────────────────────────────────────────
// Vehicles
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_VEHICLES: Vehicle[] = [
  { vehicle_id: "VEH-001", driver_name: "Rajan Kumar", driver_phone: "+91 98765 43210", plate: "KA 51 AB 1234", type: "TRUCK", status: "EN_ROUTE", coordinates: { lat: 12.812, lng: 77.686 } },
  { vehicle_id: "VEH-002", driver_name: "Suresh Nair", driver_phone: "+91 87654 32109", plate: "KA 05 TN 7890", type: "VAN", status: "AVAILABLE", coordinates: { lat: 12.8442, lng: 77.6648 } },
  { vehicle_id: "VEH-003", driver_name: "Priya Menon", driver_phone: "+91 76543 21098", plate: "TN 10 CF 5566", type: "TRUCK", status: "DELIVERED", coordinates: { lat: 12.7112, lng: 77.6954 } },
  { vehicle_id: "VEH-004", driver_name: "Arun Sharma", driver_phone: "+91 65432 10987", plate: "KA 09 MN 4455", type: "BOAT", status: "AVAILABLE" },
];

// ─────────────────────────────────────────────────────────────────────────────
// Map Markers
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_MAP_MARKERS: MapMarker[] = [
  { id: "mark-rpt-001", type: "REPORT", coordinates: [77.694, 12.798], label: "RPT-001 · Flood · 850 affected", report_id: "RPT-001", plan_id: "PLAN-2024-001", risk_level: "HIGH" },
  { id: "mark-rpt-002", type: "REPORT", coordinates: [77.701, 12.752], label: "RPT-002 · Flood · 340 affected", report_id: "RPT-002", plan_id: "PLAN-2024-002", risk_level: "HIGH" },
  { id: "mark-rpt-003", type: "REPORT", coordinates: [77.698, 12.775], label: "RPT-003 · Medical · 12 affected", report_id: "RPT-003", plan_id: "PLAN-2024-003", risk_level: "MODERATE" },
  { id: "mark-sup-01", type: "SUPPLIER", coordinates: [77.6648, 12.8442], label: "Electronic City Emergency Depot", risk_level: "LOW" },
  { id: "mark-sup-02", type: "SUPPLIER", coordinates: [77.6715, 12.836], label: "Bommasandra Logistics Hub", risk_level: "LOW" },
  { id: "mark-sup-03", type: "SUPPLIER", coordinates: [77.83, 12.74], label: "Hosur Medical Store", risk_level: "LOW" },
  { id: "mark-dc-001", type: "CENTRE", coordinates: [77.6954, 12.7112], label: "Anekal Relief Centre", risk_level: "LOW" },
  { id: "mark-dc-002", type: "CENTRE", coordinates: [77.694, 12.798], label: "Chandapura Emergency Hub", risk_level: "MODERATE" },
  { id: "mark-blocked-01", type: "BLOCKED", coordinates: [77.7025, 12.731], label: "Karpur Bridge — Structural damage reported", risk_level: "HIGH" },
  { id: "mark-veh-001", type: "VEHICLE", coordinates: [77.686, 12.812], label: "VEH-001 · Rajan Kumar · EN ROUTE", plan_id: "PLAN-2024-001", risk_level: "LOW" },
];

// ─────────────────────────────────────────────────────────────────────────────
// Audit Timeline
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_AUDIT_TIMELINE: AuditTimeline[] = [
  { event_id: "AUD-001", occurred_at: new Date(Date.now() - 5 * 3600000).toISOString(), actor: "Citizen (tg_user_412)", action: "REPORT_RECEIVED", description: "Citizen report RPT-001 received via Telegram bot. 850 people affected in Chandapura flood.", entity_id: "RPT-001", entity_type: "CitizenReport", outcome: "SUCCESS", icon_type: "report" },
  { event_id: "AUD-002", occurred_at: new Date(Date.now() - 4.9 * 3600000).toISOString(), actor: "AI Engine (Gemini 2.0)", action: "AI_EXTRACTION_COMPLETE", description: "Emergency type FLOOD identified. 4 commodities extracted. Confidence: 94%. Plan generation triggered.", entity_id: "RPT-001", entity_type: "AIExtraction", outcome: "SUCCESS", icon_type: "ai" },
  { event_id: "AUD-003", occurred_at: new Date(Date.now() - 4.7 * 3600000).toISOString(), actor: "Operator (admin-01)", action: "REPORT_VERIFIED", description: "Operator verified RPT-001 using satellite imagery cross-reference. Escalated to priority tier.", entity_id: "RPT-001", entity_type: "CitizenReport", outcome: "SUCCESS", icon_type: "verify" },
  { event_id: "AUD-004", occurred_at: new Date(Date.now() - 4.5 * 3600000).toISOString(), actor: "ReliefRoute Agent", action: "PLAN_GENERATED", description: "Delivery plan PLAN-2024-001 generated. Route via Hosur Rd avoids flood polygon. Risk: MODERATE.", entity_id: "PLAN-2024-001", entity_type: "DeliveryPlan", outcome: "SUCCESS", icon_type: "plan" },
  { event_id: "AUD-005", occurred_at: new Date(Date.now() - 4 * 3600000).toISOString(), actor: "Operator (admin-01)", action: "PLAN_APPROVED", description: "PLAN-2024-001 approved. Comment: Verified route avoids marked hazard zone. Proceed.", entity_id: "PLAN-2024-001", entity_type: "DeliveryPlan", outcome: "SUCCESS", icon_type: "approve" },
  { event_id: "AUD-006", occurred_at: new Date(Date.now() - 3.8 * 3600000).toISOString(), actor: "Dispatch System", action: "DRIVER_DISPATCHED", description: "Driver Rajan Kumar (KA 51 AB 1234) dispatched via Telegram. ETA 45 minutes to Chandapura.", entity_id: "DSP-001", entity_type: "DispatchResult", outcome: "SUCCESS", icon_type: "dispatch" },
  { event_id: "AUD-007", occurred_at: new Date(Date.now() - 3 * 3600000).toISOString(), actor: "Citizen (tg_user_789)", action: "REPORT_RECEIVED", description: "Citizen report RPT-003 received. Medical emergency — diabetic patient in Suragajakkanahalli.", entity_id: "RPT-003", entity_type: "CitizenReport", outcome: "SUCCESS", icon_type: "report" },
  { event_id: "AUD-008", occurred_at: new Date(Date.now() - 2.9 * 3600000).toISOString(), actor: "AI Engine (Gemini 2.0)", action: "AI_EXTRACTION_COMPLETE", description: "Medical commodities extracted. Confidence: 92%. Missing: specific medication names.", entity_id: "RPT-003", entity_type: "AIExtraction", outcome: "SUCCESS", icon_type: "ai" },
  { event_id: "AUD-009", occurred_at: new Date(Date.now() - 45 * 60000).toISOString(), actor: "Citizen (tg_user_1023)", action: "REPORT_RECEIVED", description: "New report RPT-004 received. Karpur bridge structural damage. 520 stranded.", entity_id: "RPT-004", entity_type: "CitizenReport", outcome: "SUCCESS", icon_type: "report" },
  { event_id: "AUD-010", occurred_at: new Date(Date.now() - 30 * 60000).toISOString(), actor: "AI Engine (Gemini 2.0)", action: "AI_EXTRACTION_COMPLETE", description: "Earthquake report RPT-005 analyzed. Confidence 68% — flagged for manual verification.", entity_id: "RPT-005", entity_type: "AIExtraction", outcome: "PENDING", icon_type: "ai" },
];

// ─────────────────────────────────────────────────────────────────────────────
// Dashboard Stats
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_DASHBOARD_STATS = {
  total_reports: 5,
  active_emergencies: 4,
  pending_approvals: 2,
  active_dispatches: 2,
  people_affected: 1922,
  delivered_today: 1,
  ai_accuracy_avg: 84,
};

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

export function getPlanById(id: string): DeliveryPlan | undefined {
  return MOCK_PLANS.find((p) => p.plan_id === id);
}

export function getReportById(id: string): CitizenReport | undefined {
  return MOCK_REPORTS.find((r) => r.report_id === id);
}

export function getAIExtractionForReport(reportId: string): AIExtraction | undefined {
  return MOCK_AI_EXTRACTIONS.find((e) => e.report_id === reportId);
}

export function getDispatchForPlan(planId: string): DispatchRecord | undefined {
  return MOCK_DISPATCHES.find((d) => d.plan_id === planId);
}
