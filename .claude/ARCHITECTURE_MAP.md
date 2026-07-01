# Architecture map

One linear Python script, `deskbird_booking.py` (~680 lines, no `main()` — it
runs at import), does everything: read env config → fetch username/password/TOTP
from **1Password CLI** (`op`) → drive **headless Chromium via Selenium** through
the Deskbird login and **Microsoft SSO** (email → password → OTP) → wait until
truly authenticated → book a desk **7 days ahead** (preferred desk first via the
"Suggestions" widget, else any available).

It ships as a container (`Dockerfile`: python:3.11-slim + chromium + chromedriver
+ 1password-cli + selenium) and runs as a **Kubernetes CronJob** in the
`automation` namespace of the **firefly** cluster. `k8s/base/cronjob.yaml` is the
spec; `k8s/overlays/prod` adds a SOPS/age-encrypted secret and pins the image tag.

CI: push to `main` → semantic-release (`.github/workflows/build-release.yaml`) →
GitHub release → image build+push to GHCR (`container-image-release.yaml`) →
**Flux** bumps the overlay tag and redeploys. No test suite, no linter.
