# Deskbird Booking Automation

Automated desk booking for [Deskbird](https://www.deskbird.com/). A single Python
script books a desk **exactly 7 days in advance** using headless Chromium
(Selenium), Microsoft SSO, and credentials pulled at runtime from 1Password.

It is packaged as a container image and runs unattended as a **Kubernetes
CronJob**.

## How it works

1. Read configuration from environment variables (`OFFICE_ID`, `FLOOR_ID`,
   optional `PREFERRED_DESK`, `OP_*`).
2. Fetch username, password, and TOTP from 1Password via the `op` CLI.
3. Drive headless Chromium through the Deskbird login and Microsoft SSO flow
   (email → password → OTP), then wait until the OAuth callback completes and the
   app is truly authenticated.
4. Navigate to the booking dashboard for the target day (7 days out) and book the
   **preferred desk** first (favourite-first "Suggestions"), falling back to any
   available desk. Skips if a booking already exists.

## Documentation

- **[Architecture](architecture.md)** — components, control flow, and the auth/booking gotchas.
- **[Setup & Deployment](setup.md)** — configuration, local runs, and the Kubernetes/CI pipeline.

!!! note "Agent context"
    Terse machine-facing context for Claude Code lives in `CLAUDE.md` and
    `.claude/*.md`, plus `PROJECT_INDEX.json`. These human docs are the
    fuller, published surface.
