# Setup & Deployment

## 1Password Integration

The script uses 1Password CLI to fetch credentials at runtime, making it fully compatible with headless Chrome.

**Requirements:**

- 1Password service account token (for CLI authentication)
- Microsoft account credentials saved in 1Password with:
  - Item name: customizable via `OP_ITEM_NAME` (default: `Deskbird`)
  - Vault: customizable via `OP_VAULT` (default: `Private`)
  - Fields: `username` (email), `password`
  - One-time password (TOTP) configured for MFA
- Deskbird office ID and floor ID (from your Deskbird workspace)

**Setup:**

1. **Create a 1Password service account**:
   - Follow: https://developer.1password.com/docs/service-accounts/get-started/
   - Grant read access to your Microsoft credentials item

2. **Find your Deskbird office and floor IDs**:
   - Log into Deskbird web app
   - Navigate to your booking page
   - Extract IDs from URL: `https://app.deskbird.com/office/{OFFICE_ID}/bookings/dashboard?floorId={FLOOR_ID}...`

## Configuration

All configuration is via environment variables, sourced in production from the
`deskbird-credentials` Kubernetes secret.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OP_SERVICE_ACCOUNT_TOKEN` | yes | — | 1Password service-account token. |
| `OP_ITEM_NAME` | no | `Deskbird` | 1Password item holding the Microsoft creds. |
| `OP_VAULT` | no | `Private` | 1Password vault name. |
| `OFFICE_ID` | yes | — | Deskbird office ID (from the booking URL). |
| `FLOOR_ID` | yes | — | Deskbird floor ID (from the booking URL). |
| `PREFERRED_DESK` | no | — | e.g. `5.09 D`. Books this desk first, else any available. |
| `BOOKING_TIMEZONE` | no | `Europe/Amsterdam` | IANA timezone for date calculations (e.g. `Europe/London`, `America/New_York`). |
| `BOOKING_WEEKDAYS` | no | `mon,thu` | Comma-separated weekday names or numbers (e.g. `mon,thu` or `0,3`; Monday=0). |
| `LOG_LEVEL` | no | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

The 1Password item must expose `username`, `password`, and a configured **TOTP**.

## Local End-to-End Testing

Use this procedure to validate a real booking flow locally before opening a PR.

### Prerequisites

- Docker is installed and running
- `secret.yaml` exists in repository root and includes:
  - `OP_SERVICE_ACCOUNT_TOKEN`
  - `OP_ITEM_NAME` (for example `Microsoft`)
- `.env` exists in repository root and includes:
  - `OFFICE_ID`
  - `FLOOR_ID`
  - optional `PREFERRED_DESK`

### 1) Syntax check

```bash
python3 -m py_compile deskbird_booking.py
```

No test suite exists; syntax validation is the primary check.

### 2) Build the local test image

```bash
docker build -t deskbird-booking:local-test .
```

### 3) Run the end-to-end booking test

This command reads the 1Password token from `secret.yaml`, passes office/floor config from `.env`, and runs the full login + booking flow:

```bash
OP_SERVICE_ACCOUNT_TOKEN=$(python3 - <<'PY'
from pathlib import Path
for line in Path('secret.yaml').read_text().splitlines():
    if line.strip().startswith('OP_SERVICE_ACCOUNT_TOKEN:'):
        print(line.split(':', 1)[1].strip())
        break
PY
) && docker run --rm \
  --env-file .env \
  -e OP_SERVICE_ACCOUNT_TOKEN="$OP_SERVICE_ACCOUNT_TOKEN" \
  -e OP_ITEM_NAME="Microsoft" \
  -e OP_VAULT="REDACTED" \
  -e LOG_LEVEL="INFO" \
  -v "$(pwd)/e2e-artifacts:/tmp" \
  deskbird-booking:local-test
```

### 4) Verify success

Successful booking run should end with:

- `✓ Clicked 'Quick book' button - booked any available desk`
- `✓ Booking completed successfully!`

If the run fails:

- Inspect logs for the failing step
- Review screenshots in `e2e-artifacts/deskbird_*.png`

## Kubernetes

### Using Kustomize (Recommended)

1. Create and encrypt your secret:
   ```bash
   cd k8s/overlays/prod
   # Copy the example and edit with your values
   cp ../../../secret.yaml.example secret.yaml
   
   # Edit secret.yaml with:
   # - OP_SERVICE_ACCOUNT_TOKEN: Your 1Password service account token
   # - OP_ITEM_NAME: Name of your 1Password item (e.g., "Microsoft")
   # - OP_VAULT: Your 1Password vault name
   # - OFFICE_ID: Your Deskbird office ID
   # - FLOOR_ID: Your Deskbird floor ID
   # - PREFERRED_DESK: (Optional) Your preferred desk name (e.g., "5.09 D")
   
   # Encrypt with SOPS
   sops -e secret.yaml > secret.enc.yaml
   rm secret.yaml  # Remove unencrypted version
   ```

2. Deploy using Kustomize:
   ```bash
   kubectl apply -k k8s/overlays/prod
   ```

3. Verify deployment:
   ```bash
   kubectl get cronjob -n automation
   kubectl get pods -n automation
   ```

The secret is encrypted with SOPS + age (`k8s/overlays/prod/.sops.yaml`). Edit the
decrypted form with `sops k8s/overlays/prod/secret.enc.yaml`; **never commit a
plaintext `secret.yaml`** (it is gitignored).

### Rendering the manifests

```bash
kubectl kustomize k8s/overlays/prod          # render/validate
```

## CI/CD

1. Push to `main` (or `staging`) → **semantic-release**
   (`.github/workflows/build-release.yaml`) analyses Conventional-Commit messages
   and cuts a versioned GitHub release. Doc/gitignore/LICENSE-only changes are
   skipped.
2. Release published → **container-image-release.yaml** builds and pushes the
   multi-arch (`linux/amd64,arm64`) image to GHCR via `docker buildx bake`.
3. **Flux** image automation bumps the tag in `k8s/overlays/prod` and reconciles
   the cluster.

Commit types that release: `fix`/`perf` → patch, `feat` → minor (see
`pyproject.toml`).

## Schedule

The CronJob schedule is configured in `k8s/base/cronjob.yaml`. Adjust as needed:
- Default: Every Monday and Thursday at 01:00 `Europe/Amsterdam` (`0 1 * * 1,4`)
- Format: Standard cron syntax

Because each run books 7 days ahead, a Monday run books the following Monday and a Thursday
run books the following Thursday. The script independently enforces this via `BOOKING_WEEKDAYS`,
so an off-schedule or manual run cannot book an unwanted day.

### Timezones must line up

Three settings have to agree, or the job books the wrong weekday:

1. **`spec.timeZone`** on the CronJob — keep it set. With it omitted, Kubernetes falls back to
   the kube-controller-manager's own clock.
2. **`BOOKING_TIMEZONE`** — the zone the script resolves "today" and the booking window in.
3. **`BOOKING_WEEKDAYS`** — must match the days in the cron expression.

If `timeZone` is unset the controller fires at 01:00 CEST, which is 23:00 UTC the
*previous* day. The container runs UTC, so it would see Sunday/Wednesday instead of Monday/Thursday —
booking Wednesdays and failing every Sunday. Both layers are now pinned to the office timezone.

## Troubleshooting

- **Authentication failures**: Check 1Password service account has read access to credentials
- **Booking failures**: Verify `OFFICE_ID` and `FLOOR_ID` are correct
- **Debug screenshots**: Check `/tmp/deskbird_*.png` in the container on failure
- **MFA issues**: Ensure TOTP is configured in your 1Password item

## Docs

```bash
pip install mkdocs-material
mkdocs serve     # preview at http://127.0.0.1:8000
mkdocs build     # static site -> ./site (gitignored)
```
