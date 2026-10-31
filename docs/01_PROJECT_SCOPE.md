# 01 — Project Scope

## Problem
Extreme rainfall and flash floods can disrupt roads and essential-goods deliveries in Karnataka. Manual monitoring and phone-based coordination are slow and fragmented. ReliefRoute connects weather information, hazard assessment, supplier-reported stock, routing, driver telemetry, approval-gated dispatch, and verification in one auditable workflow.

## Target audience
Primary: district disaster response teams and NGOs. Secondary: FPOs, APMC/market aggregators, and small fleet operators. Beneficiaries: affected communities and consumers reliant on perishable supply chains.

## Pilot
Start with Bengaluru–Anekal. Expand toward Kolar and Chikkaballapur only if the core flow is stable.

## In scope for today's demo
- Real forecast data from Open-Meteo.
- Hazard assessment with source timestamps and limitations.
- Supplier registration and supplier-reported inventory stored in the database.
- Driver GPS from a real participating phone, through Telegram or a location form.
- Candidate route calculation if provider capability and credentials are verified.
- Plan review and explicit human approval before dispatch.
- Dispatch message, acknowledgement, audit log, and visible failure states.

## Stretch goals
- Agmarknet market arrivals/prices.
- Official flood extent or satellite layer.
- Multiple suppliers and vehicle optimization.
- Automatic ETA-drift replanning.

## Non-goals
- Guaranteeing that any road is safe/passable.
- Replacing official emergency instructions.
- Inferring current supplier stock from mandi arrival data.
- Autonomous high-impact dispatch without approval.
- Presenting simulated or stale data as live data.

## Success criteria
A reviewer can trace one delivery from source data to hazard assessment, route, approval, dispatch, driver acknowledgement, and audit record. All external data has source/time metadata; unavailable integrations fail visibly.
