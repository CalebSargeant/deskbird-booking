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

- Calculates booking date (today + 7 days)
- Navigates to your configured office and floor
- Books a full-day desk (8 AM - 6 PM)
- Clicks the first available "Quick book" button
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
