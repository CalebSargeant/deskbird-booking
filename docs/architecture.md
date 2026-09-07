# Architecture

## Components

| Component | Path | Role |
|-----------|------|------|
| Booking script | `deskbird_booking.py` | The entire application — a linear script (no `main()`) that runs top-to-bottom. |
| Container | `Dockerfile` | `python:3.11-slim` + chromium + chromium-driver + 1password-cli + selenium + tzdata. |
| CronJob | `k8s/base/cronjob.yaml` | Schedule (Monday & Thursday 01:00 Europe/Amsterdam), env, resources, safety limits. |
| Prod overlay | `k8s/overlays/prod/` | Kustomize base + SOPS/age-encrypted secret; pins the image tag (Flux-managed). |
| CI | `.github/workflows/` | semantic-release + multi-arch image build/push to GHCR. |

## Control flow

The script executes as one sequence wrapped in a `try/except/finally`:

1. **Config bootstrap** — read env vars; **raises immediately if `OFFICE_ID` or
   `FLOOR_ID` is unset**. Fetch `username`/`password` from 1Password. Resolve the
   target booking date (today + 7 days) in the configured timezone. **Exit silently
   if the target date is not a configured booking weekday** (guard rail: CronJob
   fires on Mon/Thu 01:00 office-local, but the script verifies the day anyway).
2. **Browser setup** — headless Chromium via Selenium (`--headless=new`,
   `--no-sandbox`, `--disable-dev-shm-usage`, in-memory `/dev/shm`).
3. **Login + Microsoft SSO** — enter email, click through to Microsoft, enter
   password, fetch and submit the TOTP from 1Password, handle "Stay signed in?".
   Helpers: `is_microsoft_login_active`, `switch_to_microsoft_window`.
4. **Wait for real authentication** — `is_authenticated_url()` blocks until the
   browser has left `/sign-in`, `/login`, and `/authenticationHandler`, i.e. the
   OAuth callback has finished and the app has loaded (e.g. `/planning/calendar`).
5. **Book** — build the booking URL for the target day (`build_booking_url`),
   navigate, check for an existing booking, then click
   `data-testid="booking-suggestions-quick-book"` — preferred desk first via
   `card_matches_preferred`, else the first (favourite-ordered) suggestion.

## Design notes & gotchas

!!! warning "Timezone handling is critical"
    Dates are resolved in `BOOKING_TIMEZONE` (default `Europe/Amsterdam`), not the
    container's UTC clock. The CronJob fires at 01:00 office-local (e.g. 23:00 UTC
    the *previous* day), so without this the script would book for the wrong
    weekday. The `BOOKING_TIMEZONE` and CronJob `timeZone` fields must always be
    in sync. The container's `/dev/shm` includes a `tzdata` fallback so timezone
    database lookups don't fail.

!!! warning "The authentication race"
    Deskbird's post-SSO landing page (`/sign-in/landing`) briefly looks like the
    app. An earlier check only tested for the absence of `"login"`, so the script
    navigated onward before the session was established and got bounced back —
    every run failed. `is_authenticated_url()` fixes this and must stay strict.

!!! warning "Brittle UI selectors"
    Deskbird's SPA is `data-testid`-driven and has been redesigned before. Key
    hooks: `booking-suggestions-quick-book`, `booking-suggestions-card`,
    `booking-card-location` (already-booked). Re-inspect the live DOM before
    changing selectors.

!!! note "Booking weekday guard rail"
    The script skips runs where the target date (today + 7 days) is not a
    configured weekday. This provides a safety layer: even if the CronJob
    scheduler misfires or is manually triggered on the wrong day, the booking
    won't run on an unintended day.
