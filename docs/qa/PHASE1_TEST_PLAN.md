# FleetPilot Phase 1 — QA test plan (trustworthy data)

App: https://d29rco0m3jujzd.cloudfront.net/ · Tester needs her own login (see `scripts/fleet_admin.py link-user`).

Automated coverage already in the repo: `tests/test_mp91_tenancy.py`, `tests/test_mp91_device_health.py`
(backend, pytest + moto) and `fleetpilot-web/src/__tests__/` (vitest). The cases below are the manual,
end-to-end checks against the real deployment.

## Setup
1. Two accounts, each with one login: A (Ajith: "My car" + "Test Van (simulated)") and B (tester's own account
   with its own simulated device; created with `fleet_admin.py add-account / add-vehicle / link-user`).
2. Two browsers (or one normal + one private window), one login each.

## 1. Tenant isolation (highest priority)
| # | Steps | Expected |
|---|---|---|
| T1 | Sign in as B. Open Dashboard, Vehicles, Live Map, Trips. | Only B's vehicles and trips. No "My car", no "Test Van". |
| T2 | As B, open a trip URL copied from account A (`#/trips/LT-car1-…`). | "Trip not found". Nothing of A's trip shown. |
| T3 | As B, open A's vehicle URL (`#/vehicles/LV-car1`). | Not found / empty. |
| T4 | In DevTools → Network, call `GET <api>/mp91?account_id=ajith` with B's token. | Response is B's data only. |
| T5 | Sign out as A, sign in as B in the same browser. | No A data appears, even briefly (cached data is cleared on sign-out). |
| T6 | Call the API with no token, and with an expired/edited token. | 401. |

## 2. Demo / live separation
| # | Steps | Expected |
|---|---|---|
| D1 | Sign in. | No "Demo data" tags, no NorthStar names, no demo vehicles (Van 101 …). |
| D2 | Help (?) → "Explore demo data". | Amber "Demo mode" banner on every page; sample fleet shown. |
| D3 | Banner → "Back to my fleet". | Real data only again; demo changes did not touch real data. |
| D4 | Vehicles → "Add vehicle" in live mode. | Explains that vehicles are added by registering a tracker (no fake local vehicle). |

## 3. Vehicle status and freshness
| # | Steps | Expected |
|---|---|---|
| F1 | Car parked, tracker reporting (heartbeat ~20 min). | Status "Stopped", no stale warning, "last message" time shown. |
| F2 | Run `python scripts/sim_drive.py --lead 0` and watch Test Van. | "Moving" while driving; "Live · 2 s" on the Live Map. |
| F3 | Stop the sim mid-trip (Ctrl+C) and wait 3, 15 and 40 min. | Delayed after ~2 min, then Stale (status no longer "Moving"); never shows moving with old data. |
| F4 | Leave a device silent > 24 h. | "Offline". |
| F5 | Unplug the real tracker (power-disconnected alarm). | "Device error" with "tracker unplugged". |

## 4. Device data and MP91 limits
| # | Steps | Expected |
|---|---|---|
| M1 | Live Map → select car. | Tracker battery %, tracker distance, alarms (if any), last message time. |
| M2 | Open Health, Fuel, Safety, Maintenance, Analytics. | Blue "Not available with this device" notice; no invented figures. |
| M3 | Trip detail of a real trip. | Speed chart says "reported by the tracker"; Fuel "n/a"; no "Demo data" note. |

## Reporting
Log each failure with: account, browser, URL, steps, expected vs actual, screenshot, time (to match server logs).
