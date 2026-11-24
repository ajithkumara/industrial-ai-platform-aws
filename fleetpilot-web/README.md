# FleetPilot Web

React 18 + TypeScript + Vite + Tailwind + Radix (shadcn-style) + Recharts + react-leaflet.
All data is **demo data** (NorthStar Mechanical Services, Oakville ON: 15 vehicles, 15 drivers), generated deterministically in `src/data/seed.ts`.

## Run locally (Windows PowerShell)

```powershell
cd fleetpilot-web
npm install
npm run dev        # http://localhost:5173
npm run typecheck
npm test           # vitest smoke tests
npm run build      # production build in dist/
```

If `npm install` fails inside a synced/mounted folder, copy the folder to a normal local path (e.g. `C:\dev\fleetpilot-web`) and run it there.

Set `VITE_ROUTER=hash` to build with hash routing (for opening from S3/file hosting without rewrites).

## Structure

- `src/data/seed.ts` demo dataset (bump `SNAPSHOT_VERSION` after changing it; state persists in localStorage)
- `src/lib/metrics.ts` single source for all KPIs, scores and costs (every page uses it, so numbers agree)
- `src/services/api.ts` `FleetApi` interface: `LocalDemoApi` today, `HttpFleetApi` placeholder for the AWS backend
- `src/store/FleetStore.tsx` reducer store + actions
- `src/pages/*` one file per module; `src/components/*` UI, shared, layout, map, forms

## Deploy to AWS (Phase 1: sign-in + live tracker data)

```powershell
cd fleetpilot-web
$env:VITE_ROUTER="hash"; npm run build
cd ..\terraform\environments\dev-stage1
terraform plan  -var "use_fleetpilot_web=true"      # review: uploads dist/* to the web bucket, no new billable resources
terraform apply -var "use_fleetpilot_web=true"
```

Or set `use_fleetpilot_web = true` in `terraform.tfvars`. Terraform writes `config.js` (Cognito + API URL, no secrets); when it is present the app requires sign-in and polls `GET /mp91` every minute, merging your tracker vehicles (id `LV-...`, real position, status and trips) into the demo data. Rollback: set it back to `false`.

## Connecting the real backend (remaining)

Implement `HttpFleetApi` against the API Gateway (`/mp91`, Cognito JWT) and select it in `FleetStore.tsx`. Live tracker data (MP91) replaces seed values for the vehicle linked to device 7018532019; everything else stays demo until its API exists. Integrations marked "demo" never contact external systems.
