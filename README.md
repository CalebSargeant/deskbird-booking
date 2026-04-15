# Deskbird Booking Automation

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Automated desk booking for Deskbird using Selenium and Kubernetes CronJob. This script automates the process of booking a desk exactly 7 days in advance with Microsoft SSO authentication and 1Password integration.

## Features

- 🔐 **Secure Authentication**: Microsoft SSO with 1Password CLI integration
- 📅 **Automatic Scheduling**: Books desks exactly 7 days in advance
- 🏢 **Configurable**: Supports multiple offices and floors via environment variables
- 🐳 **Container-Ready**: Includes Dockerfile and Kubernetes manifests
- 🔒 **SOPS Encrypted Secrets**: Production secrets encrypted with age

## How It Works

### Authentication Flow

1. Navigates to Deskbird login page
2. Enters email and clicks "Sign in with Microsoft"
3. Handles Microsoft SSO popup with 1Password CLI:
   - Fetches credentials from 1Password at runtime
   - Enters email and password
   - Handles TOTP/MFA if required
4. Completes authentication and returns to Deskbird

### Booking Logic

- Calculates booking date (7 days ahead)
- Navigates to your configured office and floor
- Uses an office-hours-compatible full-day window (with fallback time ranges if needed)
- **Preferred desk support**: Attempts to book your preferred desk first (if configured)
- **Fallback**: Books any available desk if preferred is unavailable
- Saves debugging screenshots on failure

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

3. **Configure the Kubernetes secret** (see deployment section below)

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

### 1) Build the local test image

```bash
docker build -t deskbird-booking:local-test .
```

### 2) Run the end-to-end booking test

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

### 3) Verify success

Successful booking run should end with:

- `✓ Clicked 'Quick book' button - booked any available desk`
- `✓ Booking completed successfully!`

If the run fails:

- Inspect logs for the failing step
- Review screenshots in `e2e-artifacts/deskbird_*.png`

## Deployment

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

### Manual Deployment

1. Build and push the image:
   ```bash
   docker build -t your-registry/deskbird-booking:latest .
   docker push your-registry/deskbird-booking:latest
   ```

2. Create your secret:
   ```bash
   kubectl create secret generic deskbird-credentials \
     --from-literal=OP_SERVICE_ACCOUNT_TOKEN="your-token" \
     --from-literal=OP_ITEM_NAME="Microsoft" \
     --from-literal=OP_VAULT="Private" \
     --from-literal=OFFICE_ID="your-office-id" \
     --from-literal=FLOOR_ID="your-floor-id" \
     --from-literal=PREFERRED_DESK="5.09 D" \
     -n automation
   ```

3. Deploy the CronJob:
   ```bash
   kubectl apply -f k8s/base/cronjob.yaml
   ```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OP_SERVICE_ACCOUNT_TOKEN` | Yes | - | 1Password service account token |
| `OP_ITEM_NAME` | No | `Deskbird` | Name of 1Password item containing Microsoft credentials |
| `OP_VAULT` | No | `Private` | 1Password vault name |
| `OFFICE_ID` | Yes | - | Deskbird office ID (from URL) |
| `FLOOR_ID` | Yes | - | Deskbird floor ID (from URL) |
| `PREFERRED_DESK` | No | - | Preferred desk (e.g., "D", "5.09 D", "5.08 B"). Letter only defaults to 5.09. Books any desk if unavailable |

### Schedule

The default CronJob schedule is configured in `k8s/base/cronjob.yaml`. Adjust as needed:
- Default: Every Thursday at 8 AM UTC
- Format: Standard cron syntax

## Troubleshooting

- **Authentication failures**: Check 1Password service account has read access to credentials
- **Booking failures**: Verify `OFFICE_ID` and `FLOOR_ID` are correct
- **Debug screenshots**: Check `/tmp/deskbird_*.png` in the container on failure
- **MFA issues**: Ensure TOTP is configured in your 1Password item

## License

MIT License - see [LICENSE](LICENSE) file for details
