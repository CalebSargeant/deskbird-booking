# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Repository overview
This repository is a single-purpose automation service that books a Deskbird desk via browser automation.

- Runtime entrypoint: `deskbird_booking.py`
- Containerization: `Dockerfile`
- Deployment: Kubernetes CronJob manifests in `k8s/`
- Release automation: GitHub Actions workflows in `.github/workflows/`

There are no additional Python packages/modules in this repo; almost all behavior lives in one script.

## Core architecture (big picture)
### 1) Credential + configuration bootstrap
`deskbird_booking.py` reads configuration from environment variables (`OFFICE_ID`, `FLOOR_ID`, optional desk preferences and logging level), then retrieves credentials and OTP values from 1Password CLI (`op`).

### 2) Browser automation workflow
The script launches headless Chromium via Selenium and executes a linear flow:
- Deskbird login page interaction
- Microsoft SSO handling (including popup handling and OTP path)
- Redirect completion checks back on Deskbird

### 3) Booking flow logic
Before authentication, the script computes the target date (7 days ahead, resolved in
`BOOKING_TIMEZONE` — *not* the container's UTC clock) and exits `0` without booking unless that
date falls on a `BOOKING_WEEKDAYS` day (default `mon,thu`).

Timezone handling is load-bearing: the CronJob's `spec.timeZone` and the script's
`BOOKING_TIMEZONE` must both be the office zone. Leaving `spec.timeZone` unset makes Kubernetes
use the controller-manager's clock, which previously fired 23:00 UTC the day *before* the intended
one and booked the wrong weekday.

After authentication, the script:
- Computes the booking target date/time window (7 days ahead, full-day range)
- Builds Deskbird booking URL using office/floor IDs and timestamps
- Detects whether a booking likely already exists
- Attempts preferred desk booking first (if configured), then falls back to any available quick-book action
- Captures screenshots under `/tmp/deskbird_*.png` for troubleshooting

### 4) Runtime + deployment model
- `Dockerfile` installs Chromium, ChromeDriver, 1Password CLI, and Selenium, then runs `deskbird_booking.py`
- `k8s/base/cronjob.yaml` schedules recurring runs and injects credentials/config from `deskbird-credentials` secret
- `k8s/overlays/prod/kustomization.yaml` composes base resources and encrypted secret for production namespace deployment

## Common commands
Run all commands from repository root.

### Local Python execution
Install dependency used by the script:
```bash
pip install selenium
```

Run the automation locally (requires Chromium/ChromeDriver and 1Password CLI available, plus required env vars):
```bash
python deskbird_booking.py
```

### Container build and run
Build image:
```bash
docker build -t deskbird-booking:local .
```

Run container (example with required env vars):
```bash
docker run --rm \
  -e OP_SERVICE_ACCOUNT_TOKEN="$OP_SERVICE_ACCOUNT_TOKEN" \
  -e OP_ITEM_NAME="Deskbird" \
  -e OP_VAULT="Private" \
  -e OFFICE_ID="$OFFICE_ID" \
  -e FLOOR_ID="$FLOOR_ID" \
  deskbird-booking:local
```

### Kubernetes deployment
Deploy production overlay:
```bash
kubectl apply -k k8s/overlays/prod
```

Inspect scheduled job:
```bash
kubectl get cronjob -n automation
kubectl get jobs -n automation
kubectl get pods -n automation
```

### Tests and linting
This repository currently has no checked-in test suite or lint configuration (no `tests/`, `pytest` config, or linter config files). Do not assume `pytest`, `ruff`, or other tooling commands exist until they are added.

## CI/CD and versioning notes
- `.github/workflows/build-release.yaml` runs semantic release on `main`/`staging` pushes (excluding doc/license/gitignore-only changes).
- `.github/workflows/container-image-release.yaml` builds/pushes GHCR container images on release publication.
- Version is tracked in `pyproject.toml` under `[tool.semantic_release]`.
