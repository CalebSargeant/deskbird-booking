# Architecture

## Components

| Component | Path | Role |
|-----------|------|------|
| Booking script | `deskbird_booking.py` | The entire application — a linear script (no `main()`) that runs top-to-bottom. |
| Container | `Dockerfile` | `python:3.11-slim` + chromium + chromium-driver + 1password-cli + selenium. |
| CronJob | `k8s/base/cronjob.yaml` | Schedule, env from the `deskbird-credentials` secret, resources, safety limits. |
| Prod overlay | `k8s/overlays/prod/` | Kustomize base + SOPS/age-encrypted secret; pins the image tag (Flux-managed). |
| CI | `.github/workflows/` | semantic-release + multi-arch image build/push to GHCR. |

## Control flow

The script executes as one sequence wrapped in a `try/except/finally`:

1. **Config bootstrap** — read env vars; **raises immediately if `OFFICE_ID` or
   `FLOOR_ID` is unset**. Fetch `username`/`password` from 1Password.
2. **Browser setup** — headless Chromium via Selenium (`--headless=new`,
   `--no-sandbox`, `--disable-dev-shm-usage`, in-memory `/dev/shm`).
3. **Login + Microsoft SSO** — enter email, click through to Microsoft, enter
   password, fetch and submit the TOTP from 1Password, handle "Stay signed in?".
   Helpers: `is_microsoft_login_active`, `switch_to_microsoft_window`.
4. **Wait for real authentication** — `is_authenticated_url()` blocks until the
   browser has left `/sign-in`, `/login`, and `/authenticationHandler`, i.e. the
   OAuth callback has finished and the app has loaded (e.g. `/planning/calendar`).
5. **Book** — compute the target day (today + 7), build the booking URL
   (`build_booking_url`), navigate, check for an existing booking, then click
   `data-testid="booking-suggestions-quick-book"` — preferred desk first via
   `card_matches_preferred`, else the first (favourite-ordered) suggestion.

## Design notes & gotchas

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

!!! note "Timezone"
    Times are computed in the container's timezone (UTC), so a "full day" booking
    surfaces as e.g. 10:00–19:00 CEST. The full-day toggle / URL params keep it a
    whole-day reservation.
