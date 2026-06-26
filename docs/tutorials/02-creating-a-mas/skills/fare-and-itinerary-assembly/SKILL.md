<!--
  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
  SPDX-License-Identifier: Apache-2.0
-->
---
name: fare-and-itinerary-assembly
description: >
  Fare lookup, cost estimation, budget-gate enforcement, city-consistency
  check, and day-by-day itinerary assembly for the Concierge Agent.
metadata:
  version: "1.0.0"
  domain: travel
  tags: [fares, budget, assembly, concierge]
---

# Fare & Itinerary Assembly Protocol

## Input
- A `FareQuery` listing route legs (`route_id` + `travel_class` for each hop).
- `RouteOptions` with the chosen route topology from `itinerary_agent`.

## Step 1 — Fare Lookup
For each leg in `FareQuery`, call `get_fares(route_id, travel_class)`.
Record the returned `fare_usd` for each leg.

## Step 2 — City Consistency Check (C5)
For every leg, verify that the destination city in the fare record matches
the destination city declared in the corresponding `RouteOptions` hop.
If any mismatch is detected:
- **HALT** assembly immediately.
- Emit `{"error": "C5_VIOLATION", "leg": "...", "detail": "..."}`
- Do NOT continue.

## Step 3 — Cost Aggregation
Call `calc` to sum transport fares across all legs.
Add `typical_day_cost_usd × trip_duration_days` for attraction and accommodation costs.

## Step 4 — Budget Gate (C7)
If `total_cost_usd > 1200`:
- Set `budget_compliant: false`.
- Set `human_review_note: "⚠️ HUMAN APPROVAL REQUIRED: budget exceeds $1200"`.
- Do NOT suppress or round the cost. Surface the gate clearly.

## Step 5 — Day-by-Day Assembly
Build a `days[]` array with one entry per day:
- `transport`: route_id, mode, fare_usd for the travel day.
- `activities`: top 2–3 attractions for the destination city.
- `daily_cost_usd`: transport + estimated activity cost.

## Privilege Isolation (C4)
You may ONLY use `get_fares` and `calc`.
Do NOT attempt booking, reservation, payment, or schedule tools.
Runtime will reject any unlisted tool call.

## Output: `FareResult`
```json
{
  "type": "FareResult",
  "origin": "...",
  "destination": "...",
  "travel_class": "Standard|Express|NightTrain_couchette",
  "fare_breakdown": [{"leg": "...", "route_id": "...", "fare_usd": 0.0}],
  "total_transport_cost_usd": 0.0,
  "total_cost_usd": 0.0,
  "budget_compliant": true,
  "city_consistency": true,
  "days": [{"day": 1, "transport": {...}, "activities": ["..."], "daily_cost_usd": 0.0}],
  "human_review_note": null
}
```
