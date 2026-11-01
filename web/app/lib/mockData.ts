// app/lib/mockData.ts
// Single source of truth for mock data in ReliefRoute.
// Built for hackathon demonstration with 5 diverse emergency logistics scenarios.

import type {
  DeliveryPlan,
  ActiveFloodArea,
  PlanStatus,
} from "@/app/types/api";

// ─────────────────────────────────────────────────────────────────────────────
// Supplemental Types
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
  ai_confidence: number;
  missing_info: string[];
  processed_at: string;
}

export interface Supplier {
  supplier_id: string;
  name: string;
  category: "MEDICAL" | "FOOD_WATER" | "SHELTER" | "EQUIPMENT" | "HYGIENE";
  contact_person: string;
  phone: string;
  email: string;
  address: string;
  coordinates: { lat: number; lng: number };
  verified: boolean;
  active: boolean;
  inventory_summary: { commodity: string; available_qty: number; unit: string }[];
}

export interface DistributionCentre {
  centre_id: string;
  name: string;
  district: string;
  coordinates: { lat: number; lng: number };
  capacity_metric_tonnes: number;
  current_utilization_pct: number;
  manager_name: string;
  phone: string;
  status: "OPERATIONAL" | "REACHING_CAPACITY" | "ISOLATED_BY_FLOOD";
}

export interface Vehicle {
  vehicle_id: string;
  type: "TRUCK_4X4" | "BOAT" | "AMBULANCE" | "DRONE_CARGO" | "TRACTOR";
  registration: string;
  capacity_kg: number;
  driver_name: string;
  driver_phone: string;
  current_location: { lat: number; lng: number };
  status: "AVAILABLE" | "EN_ROUTE" | "LOADING" | "MAINTENANCE";
}

export interface DispatchRecord {
  dispatch_id: string;
  plan_id: string;
  dispatched_at: string;
  vehicle_id: string;
  driver_name: string;
  driver_phone: string;
  status: "DISPATCHED" | "ACKNOWLEDGED" | "IN_TRANSIT" | "DELIVERED" | "REROUTED";
  estimated_arrival: string;
  current_location?: { lat: number; lng: number };
  notes: string;
}

export interface MapMarker {
  id: string;
  type: "REPORT" | "SUPPLIER" | "CENTRE" | "VEHICLE" | "HAZARD_FLAG";
  coordinates: [number, number]; // [lng, lat]
  label: string;
  severity?: "CRITICAL" | "HIGH" | "MODERATE" | "LOW";
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
  entity_type: "CitizenReport" | "DeliveryPlan" | "ApprovalDecision" | "DispatchInstruction" | "HazardAssessment";
  outcome: "SUCCESS" | "FLAGGED" | "BLOCKED" | "RETRYING";
  icon_type: "report" | "ai" | "hazard" | "route" | "approve" | "dispatch" | "verify";
}

// ─────────────────────────────────────────────────────────────────────────────
// 5 Diverse Hackathon Plans (Bangalore South / Anekal Corridor)
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_PLANS: DeliveryPlan[] = [
  // 1. PLAN-2024-001: DISPATCHED (Completed live cycle demonstration)
  {
    plan_id: "PLAN-2024-001",
    created_at: new Date(Date.now() - 4 * 3600000).toISOString(),
    supplier_id: "supplier-electronic-city-01",
    commodity: "Emergency Drinking Water & Ready-to-Eat Meal Packs",
    quantity: 850,
    unit: "crates",
    origin: { latitude: 12.8442, longitude: 77.6648 }, // Electronic City Phase 1
    destination: { latitude: 12.798, longitude: 77.694 }, // Chandapura Relief Site
    status: "DISPATCHED",
    approval_required: true,
    idempotency_key: "idemp-plan-001",
    hazard_assessment_id: "haz-001",
    rationale: [
      "Autonomous plan synthesized from verified citizen distress reports.",
      "Primary route safely bypasses Muthanallur drainage basin with 1.8km clearance.",
      "Approved by Human Operator (admin-01) and successfully dispatched via Telegram bot.",
    ],
    source_refs: [
      {
        provider: "Open-Meteo & Central Water Commission",
        url: "https://api.open-meteo.com",
        retrieved_at: new Date(Date.now() - 4 * 3600000).toISOString(),
        stale: false,
        notes: "Real-time precipitation modeling (>45mm/hr)",
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
        ],
      },
      distance_m: 14200,
      duration_s: 1320,
      avoids_requested_polygons: true,
      risk_level: "LOW",
      warnings: ["High traffic on elevated expressway bypass; hazard clearance confirmed"],
      source: {
        provider: "openrouteservice",
        retrieved_at: new Date(Date.now() - 4 * 3600000).toISOString(),
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
      emergency_type: "FLASH FLOOD & INUNDATION",
      requested_supplies: [
        "Drinking Water Purification Units",
        "Ready-to-Eat Emergency Meals",
        "Trauma Kits",
      ],
      extracted_location: "Chandapura Basin Relief Sector",
      original_message:
        "Water level crossed 1.5 meters near Chandapura circle! More than 800 citizens trapped in school building without food and potable water. Please send help!",
      confidence: 98.2,
      people_affected: 850,
    },
  },

  // 2. PLAN-2024-002: PENDING_APPROVAL, Risk HIGH (Visibly intersects hazard, locks dispatch!)
  {
    plan_id: "PLAN-2024-002",
    created_at: new Date(Date.now() - 2.5 * 3600000).toISOString(),
    supplier_id: "supplier-bommasandra-02",
    commodity: "Thermal Blankets & Emergency Clothing Bundles",
    quantity: 800,
    unit: "bundles",
    origin: { latitude: 12.836, longitude: 77.6715 }, // Bommasandra Logistics Park
    destination: { latitude: 12.752, longitude: 77.701 }, // Marsur Village Center
    status: "PENDING_APPROVAL",
    approval_required: true,
    idempotency_key: "idemp-plan-002",
    hazard_assessment_id: "haz-002",
    rationale: [
      "CRITICAL HAZARD INTERSECTION: Shortest ground path intersects active 2.1m flood polygon.",
      "Autonomous dispatch locked: human operator must review and confirm alternate detour.",
      "Marsur village isolated with 340 individuals requiring immediate thermal protection.",
    ],
    source_refs: [
      {
        provider: "Open-Meteo & Radar Hydrology",
        url: "https://api.open-meteo.com",
        retrieved_at: new Date(Date.now() - 2.5 * 3600000).toISOString(),
        stale: false,
        notes: "Flash flood surge warning across Marsur drainage channel",
      },
    ],
    route: {
      provider: "openrouteservice",
      geometry: {
        type: "LineString",
        // Notice coordinate [77.698, 12.775] sits directly inside polygon [77.685-77.715, 12.760-12.785]!
        coordinates: [
          [77.6715, 12.836],
          [77.686, 12.812],
          [77.698, 12.775],
          [77.701, 12.752],
        ],
      },
      distance_m: 10200,
      duration_s: 1140,
      avoids_requested_polygons: false,
      risk_level: "HIGH",
      warnings: [
        "CRITICAL: Direct path crosses submerged 2.1m flood hazard zone near Marsur Road",
        "Vehicle dispatch locked until human operator signs off on reroute",
      ],
      source: {
        provider: "openrouteservice",
        retrieved_at: new Date(Date.now() - 2.5 * 3600000).toISOString(),
        stale: false,
      },
    },
    hazard_polygons: [
      {
        type: "Polygon",
        coordinates: [
          [
            [77.685, 12.785],
            [77.715, 12.785],
            [77.72, 12.765],
            [77.69, 12.76],
            [77.685, 12.785],
          ],
        ],
      },
    ],
    gen_ai_extraction: {
      emergency_type: "VILLAGE ISOLATION & FLOODING",
      requested_supplies: ["Thermal Blankets", "Clothing Bundles", "Waterproof Tarpaulins"],
      extracted_location: "Marsur Village Centre (Anekal)",
      original_message:
        "Marsur village completely isolated, lake overflowed, houses submerged. 340 people cold and wet, please send blankets and clothing.",
      confidence: 95.2,
      people_affected: 340,
    },
  },

  // 3. PLAN-2024-003: PENDING_APPROVAL, Risk LOW (Route curves clearly around hazard!)
  {
    plan_id: "PLAN-2024-003",
    created_at: new Date(Date.now() - 1.2 * 3600000).toISOString(),
    supplier_id: "supplier-hosur-medical-03",
    commodity: "Insulin (Rapid-Acting) & Emergency Trauma Kits",
    quantity: 60,
    unit: "kits",
    origin: { latitude: 12.8442, longitude: 77.6648 }, // Electronic City Phase 1
    destination: { latitude: 12.715, longitude: 77.698 }, // Anekal South Shelter
    status: "PENDING_APPROVAL",
    approval_required: true,
    idempotency_key: "idemp-plan-003",
    hazard_assessment_id: "haz-003",
    rationale: [
      "Life-critical medical emergency: AI obstacle avoidance rerouted through western Jigani corridor.",
      "Route visibly arcs around Suragajakkanahalli-Karpur flood basin with 2.2km safety margin.",
      "Zero intersection with active hazard polygons; ready for immediate operator authorization.",
    ],
    source_refs: [
      {
        provider: "Open-Meteo & Health Crisis Response",
        url: "https://api.open-meteo.com",
        retrieved_at: new Date(Date.now() - 1.2 * 3600000).toISOString(),
        stale: false,
        notes: "Time-critical delivery window < 90 mins",
      },
    ],
    route: {
      provider: "openrouteservice",
      geometry: {
        type: "LineString",
        // Bends safely WEST to avoid the Suragajakkanahalli-Karpur hazard polygon!
        coordinates: [
          [77.6648, 12.8442],
          [77.652, 12.818],
          [77.648, 12.785],
          [77.653, 12.752],
          [77.665, 12.73],
          [77.685, 12.718],
          [77.698, 12.715],
        ],
      },
      distance_m: 16800,
      duration_s: 1540,
      avoids_requested_polygons: true,
      risk_level: "LOW",
      warnings: ["Successfully routed via western Jigani bypass; all flood polygons avoided"],
      source: {
        provider: "openrouteservice",
        retrieved_at: new Date(Date.now() - 1.2 * 3600000).toISOString(),
        stale: false,
      },
    },
    hazard_polygons: [
      {
        type: "Polygon",
        coordinates: [
          [
            [77.68, 12.78],
            [77.712, 12.78],
            [77.715, 12.745],
            [77.682, 12.745],
            [77.68, 12.78],
          ],
        ],
      },
    ],
    gen_ai_extraction: {
      emergency_type: "CRITICAL MEDICAL EMERGENCY",
      requested_supplies: [
        "Rapid-Acting Insulin Vials",
        "Syringes & Glucometers",
        "Sterile Trauma Kits",
      ],
      extracted_location: "Anekal South Relief Sector",
      original_message:
        "Urgent SOS: Multiple elderly diabetes patients trapped at Anekal South shelter without insulin for 18 hours. Blood sugar spiking dangerously, need insulin kits immediately!",
      confidence: 99.1,
      people_affected: 120,
    },
  },

  // 4. PLAN-2024-004: NEEDS_APPROVAL, Risk MODERATE (Lake Overflow & Water Contamination)
  {
    plan_id: "PLAN-2024-004",
    created_at: new Date(Date.now() - 45 * 60000).toISOString(),
    supplier_id: "supplier-electronic-city-01",
    commodity: "Water Purification Drops & High-Calorie Rations",
    quantity: 500,
    unit: "crates",
    origin: { latitude: 12.8442, longitude: 77.6648 }, // Electronic City Depot
    destination: { latitude: 12.822, longitude: 77.728 }, // Muthanallur Primary School
    status: "NEEDS_APPROVAL",
    approval_required: true,
    idempotency_key: "idemp-plan-004",
    hazard_assessment_id: "haz-004",
    rationale: [
      "Muthanallur Lake bund overflow reported across 14 independent citizen Telegram alerts.",
      "Drinking water contamination risk: route scheduled along northern elevated perimeter.",
      "Human validation required to confirm northern bridge structural capacity.",
    ],
    source_refs: [
      {
        provider: "Open-Meteo & Central Water Commission",
        url: "https://api.open-meteo.com",
        retrieved_at: new Date(Date.now() - 45 * 60000).toISOString(),
        stale: false,
        notes: "Lake water level +0.9m above crest",
      },
    ],
    route: {
      provider: "openrouteservice",
      geometry: {
        type: "LineString",
        coordinates: [
          [77.6648, 12.8442],
          [77.685, 12.839],
          [77.705, 12.831],
          [77.728, 12.822],
        ],
      },
      distance_m: 8900,
      duration_s: 980,
      avoids_requested_polygons: true,
      risk_level: "MODERATE",
      warnings: ["Minor water runoff along Muthanallur approach road"],
      source: {
        provider: "openrouteservice",
        retrieved_at: new Date(Date.now() - 45 * 60000).toISOString(),
        stale: false,
      },
    },
    hazard_polygons: [
      {
        type: "Polygon",
        coordinates: [
          [
            [77.715, 12.835],
            [77.745, 12.835],
            [77.75, 12.81],
            [77.72, 12.805],
            [77.715, 12.835],
          ],
        ],
      },
    ],
    gen_ai_extraction: {
      emergency_type: "LAKE OVERFLOW & DRINKING WATER CONTAMINATION",
      requested_supplies: [
        "Chlorine Tablets & Purification Kits",
        "Clean Bottled Water",
        "ORS Hydration Sachets",
      ],
      extracted_location: "Muthanallur Lake Periphery (Anekal East)",
      original_message:
        "Muthanallur lake has breached its bund! Contaminated flood water entered village open wells. Over 250 villagers have no drinking water since morning.",
      confidence: 96.3,
      people_affected: 260,
    },
  },

  // 5. PLAN-2024-005: NEEDS_APPROVAL, Risk MODERATE (Maternal Distress & Inflatable Rafts)
  {
    plan_id: "PLAN-2024-005",
    created_at: new Date(Date.now() - 20 * 60000).toISOString(),
    supplier_id: "supplier-bommasandra-02",
    commodity: "Inflatable Rescue Rafts & Maternal Emergency Delivery Packs",
    quantity: 25,
    unit: "units",
    origin: { latitude: 12.836, longitude: 77.6715 }, // Bommasandra Logistics Park
    destination: { latitude: 12.86, longitude: 77.785 }, // Sarjapur Lowland Hamlet
    status: "NEEDS_APPROVAL",
    approval_required: true,
    idempotency_key: "idemp-plan-005",
    hazard_assessment_id: "haz-005",
    rationale: [
      "Urgent maternal evacuation: 3 pregnant women stranded on building rooftops.",
      "Route utilizes Sarjapur-Attibele ridge road with inflatable rescue raft transport.",
      "Operator authorization requested to initiate combined 4x4 and motorized raft deployment.",
    ],
    source_refs: [
      {
        provider: "Open-Meteo & NDMA District Advisory",
        url: "https://api.open-meteo.com",
        retrieved_at: new Date(Date.now() - 20 * 60000).toISOString(),
        stale: false,
        notes: "Heavy thunderstorm over Sarjapur basin",
      },
    ],
    route: {
      provider: "openrouteservice",
      geometry: {
        type: "LineString",
        coordinates: [
          [77.6715, 12.836],
          [77.702, 12.845],
          [77.738, 12.852],
          [77.765, 12.857],
          [77.785, 12.86],
        ],
      },
      distance_m: 16800,
      duration_s: 1720,
      avoids_requested_polygons: true,
      risk_level: "MODERATE",
      warnings: ["Heavy surface pooling along Attibele-Sarjapur link road"],
      source: {
        provider: "openrouteservice",
        retrieved_at: new Date(Date.now() - 20 * 60000).toISOString(),
        stale: false,
      },
    },
    hazard_polygons: [
      {
        type: "Polygon",
        coordinates: [
          [
            [77.76, 12.875],
            [77.805, 12.875],
            [77.81, 12.845],
            [77.765, 12.84],
            [77.76, 12.875],
          ],
        ],
      },
    ],
    gen_ai_extraction: {
      emergency_type: "ISOLATED HAMLET & MATERNAL MEDICAL DISTRESS",
      requested_supplies: [
        "Inflatable Rescue Rafts",
        "Maternal Delivery Kits",
        "Sterile Baby Warmers",
      ],
      extracted_location: "Sarjapur Lowland Settlement (Sector 4)",
      original_message:
        "Emergency at Sarjapur lowland hamlet: 3 pregnant women and 40 children stranded on rooftops with water at 1.8m. Need inflatable rescue rafts and maternal kits urgently!",
      confidence: 98.7,
      people_affected: 180,
    },
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Active Flood Areas (Displayed as markers & drawer cards on /map)
// ─────────────────────────────────────────────────────────────────────────────

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
    coordinates: [77.698, 12.715],
    severity: "HIGH",
    water_level: "Flash flood runoff",
    commodity: "Insulin & Medical Kits",
    status: "PENDING_APPROVAL",
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
    people_affected: 180,
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Citizen Reports (Telegram Bot Feed)
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_REPORTS: CitizenReport[] = [
  {
    report_id: "RPT-001",
    submitted_at: new Date(Date.now() - 5 * 3600000).toISOString(),
    emergency_type: "FLOOD",
    description: "Water level crossed 1.5m near Chandapura circle! More than 800 citizens trapped in school building without food and potable water.",
    location: "Chandapura Circle, Bengaluru South",
    coordinates: { lat: 12.798, lng: 77.694 },
    people_affected: 850,
    required_assistance: ["Drinking Water", "Food Packs", "First Aid"],
    status: "DISPATCHED",
    anonymous: false,
    telegram_user_id: "tg_user_412",
    ai_confidence: 98.2,
  },
  {
    report_id: "RPT-002",
    submitted_at: new Date(Date.now() - 3 * 3600000).toISOString(),
    emergency_type: "FLOOD",
    description: "Marsur village completely isolated, lake overflowed, houses submerged. 340 people cold and wet, please send blankets and clothing.",
    location: "Marsur Village Center, Anekal Taluk",
    coordinates: { lat: 12.752, lng: 77.701 },
    people_affected: 340,
    required_assistance: ["Thermal Blankets", "Clothing", "Dry Rations"],
    status: "PLAN_GENERATED",
    anonymous: false,
    telegram_user_id: "tg_user_589",
    ai_confidence: 95.2,
  },
  {
    report_id: "RPT-003",
    submitted_at: new Date(Date.now() - 1.5 * 3600000).toISOString(),
    emergency_type: "MEDICAL",
    description: "Urgent SOS: Multiple elderly diabetes patients trapped at Anekal South shelter without insulin for 18 hours. Blood sugar spiking dangerously!",
    location: "Anekal South Relief Sector",
    coordinates: { lat: 12.715, lng: 77.698 },
    people_affected: 120,
    required_assistance: ["Insulin", "Medical Trauma Kits"],
    status: "PLAN_GENERATED",
    anonymous: false,
    telegram_user_id: "tg_user_789",
    ai_confidence: 99.1,
  },
  {
    report_id: "RPT-004",
    submitted_at: new Date(Date.now() - 50 * 60000).toISOString(),
    emergency_type: "FLOOD",
    description: "Muthanallur lake has breached its bund! Contaminated flood water entered village open wells. Over 250 villagers have no drinking water.",
    location: "Muthanallur Lake Periphery",
    coordinates: { lat: 12.822, lng: 77.728 },
    people_affected: 260,
    required_assistance: ["Water Purification Drops", "Potable Water"],
    status: "VERIFIED",
    anonymous: true,
    ai_confidence: 96.3,
  },
  {
    report_id: "RPT-005",
    submitted_at: new Date(Date.now() - 25 * 60000).toISOString(),
    emergency_type: "MEDICAL",
    description: "Emergency at Sarjapur lowland hamlet: 3 pregnant women and 40 children stranded on rooftops with water at 1.8m. Need inflatable rescue rafts!",
    location: "Sarjapur Lowland Settlement",
    coordinates: { lat: 12.86, lng: 77.785 },
    people_affected: 180,
    required_assistance: ["Inflatable Rafts", "Maternal Delivery Kits"],
    status: "VERIFIED",
    anonymous: false,
    telegram_user_id: "tg_user_102",
    ai_confidence: 98.7,
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Dispatches, Suppliers & Fleet Data
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_DISPATCHES: DispatchRecord[] = [
  {
    dispatch_id: "DSP-001",
    plan_id: "PLAN-2024-001",
    dispatched_at: new Date(Date.now() - 3.5 * 3600000).toISOString(),
    vehicle_id: "VEH-TRUCK-01",
    driver_name: "Ramesh Gowda",
    driver_phone: "+91 98450 12345",
    status: "IN_TRANSIT",
    estimated_arrival: new Date(Date.now() + 20 * 60000).toISOString(),
    current_location: { lat: 12.825, lng: 77.678 },
    notes: "Driver acknowledged via Telegram. En-route on elevated expressway corridor.",
  },
];

export const MOCK_SUPPLIERS: Supplier[] = [
  {
    supplier_id: "supplier-electronic-city-01",
    name: "Red Cross Logistics Hub — Electronic City",
    category: "FOOD_WATER",
    contact_person: "Dr. Ananya Sharma",
    phone: "+91 98450 88990",
    email: "ananya.sharma@redcross.org.in",
    address: "Plot 42, Electronic City Phase 1, Bengaluru",
    coordinates: { lat: 12.8442, lng: 77.6648 },
    verified: true,
    active: true,
    inventory_summary: [
      { commodity: "Drinking Water (20L Cans)", available_qty: 1200, unit: "cans" },
      { commodity: "Meal Packs (MRE)", available_qty: 3500, unit: "packs" },
    ],
  },
  {
    supplier_id: "supplier-bommasandra-02",
    name: "Karnataka State Disaster Relief Depot — Bommasandra",
    category: "SHELTER",
    contact_person: "Suresh Patil",
    phone: "+91 98451 22334",
    email: "ksdma.bommasandra@karnataka.gov.in",
    address: "Industrial Area Phase 2, Bommasandra, Bengaluru",
    coordinates: { lat: 12.836, lng: 77.6715 },
    verified: true,
    active: true,
    inventory_summary: [
      { commodity: "Thermal Blankets", available_qty: 2400, unit: "bundles" },
      { commodity: "Tarpaulins (Heavy-Duty)", available_qty: 800, unit: "sheets" },
    ],
  },
  {
    supplier_id: "supplier-hosur-medical-03",
    name: "Apollo Emergency Medical Depot — Hosur Border",
    category: "MEDICAL",
    contact_person: "Dr. Rajesh Nair",
    phone: "+91 98452 44556",
    email: "rajesh.nair@apolloemergency.in",
    address: "Border Medical Zone, Hosur-Anekal Rd",
    coordinates: { lat: 12.74, lng: 77.83 },
    verified: true,
    active: true,
    inventory_summary: [
      { commodity: "Rapid-Acting Insulin Vials", available_qty: 150, unit: "kits" },
      { commodity: "Trauma Surgical Packs", available_qty: 400, unit: "packs" },
    ],
  },
];

export const MOCK_CENTRES: DistributionCentre[] = [
  {
    centre_id: "DC-01",
    name: "Central Anekal Emergency Relief Hub",
    district: "Bengaluru Urban",
    coordinates: { lat: 12.7112, lng: 77.6954 },
    capacity_metric_tonnes: 150,
    current_utilization_pct: 68,
    manager_name: "Pooja Hegde",
    phone: "+91 98453 66778",
    status: "OPERATIONAL",
  },
];

export const MOCK_VEHICLES: Vehicle[] = [
  {
    vehicle_id: "VEH-TRUCK-01",
    type: "TRUCK_4X4",
    registration: "KA-51-E-9021",
    capacity_kg: 3500,
    driver_name: "Ramesh Gowda",
    driver_phone: "+91 98450 12345",
    current_location: { lat: 12.825, lng: 77.678 },
    status: "EN_ROUTE",
  },
  {
    vehicle_id: "VEH-TRUCK-02",
    type: "TRUCK_4X4",
    registration: "KA-51-E-4412",
    capacity_kg: 4000,
    driver_name: "Mohan Kumar",
    driver_phone: "+91 98450 67890",
    current_location: { lat: 12.836, lng: 77.6715 },
    status: "AVAILABLE",
  },
];

export const MOCK_AUDIT_TIMELINE: AuditTimeline[] = [
  {
    event_id: "AUD-001",
    occurred_at: new Date(Date.now() - 5 * 3600000).toISOString(),
    actor: "Citizen (tg_user_412)",
    action: "REPORT_RECEIVED",
    description: "Citizen report RPT-001 ingested via Telegram bot. 850 people affected in Chandapura flood.",
    entity_id: "RPT-001",
    entity_type: "CitizenReport",
    outcome: "SUCCESS",
    icon_type: "report",
  },
  {
    event_id: "AUD-002",
    occurred_at: new Date(Date.now() - 4.8 * 3600000).toISOString(),
    actor: "ReliefRoute Gen AI Triage",
    action: "NATURAL_LANGUAGE_STRUCTURED",
    description: "LLM extraction completed with 98.2% confidence. Identified: 850 water/food kits at Chandapura.",
    entity_id: "RPT-001",
    entity_type: "CitizenReport",
    outcome: "SUCCESS",
    icon_type: "ai",
  },
  {
    event_id: "AUD-003",
    occurred_at: new Date(Date.now() - 4.5 * 3600000).toISOString(),
    actor: "Open-Meteo & Radar Agent",
    action: "HAZARD_POLYGON_MAPPED",
    description: "Muthanallur-Chandapura flood basin generated. High precipitation (>45mm/hr) detected.",
    entity_id: "haz-001",
    entity_type: "HazardAssessment",
    outcome: "SUCCESS",
    icon_type: "hazard",
  },
  {
    event_id: "AUD-004",
    occurred_at: new Date(Date.now() - 4.2 * 3600000).toISOString(),
    actor: "OpenRouteService Routing Engine",
    action: "OBSTACLE_AVOIDANCE_ROUTED",
    description: "Generated flood-safe route LineString avoiding hazard polygon with 1.8km clearance.",
    entity_id: "PLAN-2024-001",
    entity_type: "DeliveryPlan",
    outcome: "SUCCESS",
    icon_type: "route",
  },
  {
    event_id: "AUD-005",
    occurred_at: new Date(Date.now() - 4 * 3600000).toISOString(),
    actor: "Operator (admin-01)",
    action: "PLAN_APPROVED",
    description: "Human operator validated rationale and granted dispatch authorization.",
    entity_id: "PLAN-2024-001",
    entity_type: "ApprovalDecision",
    outcome: "SUCCESS",
    icon_type: "approve",
  },
  {
    event_id: "AUD-006",
    occurred_at: new Date(Date.now() - 3.5 * 3600000).toISOString(),
    actor: "Telegram Dispatch Bot",
    action: "DISPATCH_COMMITTED",
    description: "Turn-by-turn navigation sent to Driver Ramesh Gowda (KA-51-E-9021).",
    entity_id: "DSP-001",
    entity_type: "DispatchInstruction",
    outcome: "SUCCESS",
    icon_type: "dispatch",
  },
];

export const MOCK_DASHBOARD_STATS = {
  active_emergencies: 5,
  citizens_assisted: 1750,
  supplies_dispatched_tonnes: 42.8,
  active_drivers: 8,
  avg_dispatch_latency_mins: 1.4,
  flood_zones_monitored: 5,
};

// ─────────────────────────────────────────────────────────────────────────────
// Lookup Helpers
// ─────────────────────────────────────────────────────────────────────────────

export function getPlanById(planId: string): DeliveryPlan | undefined {
  return MOCK_PLANS.find((p) => p.plan_id.toLowerCase() === planId.toLowerCase());
}

export function getReportById(reportId: string): CitizenReport | undefined {
  return MOCK_REPORTS.find((r) => r.report_id.toLowerCase() === reportId.toLowerCase());
}

export function getAuditByEntityId(entityId: string): AuditTimeline[] {
  return MOCK_AUDIT_TIMELINE.filter(
    (a) => a.entity_id.toLowerCase() === entityId.toLowerCase()
  );
}
