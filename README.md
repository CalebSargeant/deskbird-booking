# Deskbird Booking Automation

Automated desk booking for Deskbird using Selenium and Kubernetes CronJob.

## Authentication Flow

1. Enter email at https://app.deskbird.com/login/check-in
2. Click "Sign in with Microsoft"
3. **1Password handles the rest:** email, password, and TOTP auto-fill

## Booking Logic

- Books a desk exactly 7 days in advance
- Targets floor 41424 in office 14205
- Full-day booking
- Clicks the first available "Quick book" option

## 1Password Integration

The script uses 1Password CLI to fetch credentials at runtime, making it fully compatible with headless Chrome.

**Requirements:**
- 1Password service account token (for CLI authentication)
- Microsoft account credentials saved in 1Password with:
  - Item name: `Deskbird` (or customize via `OP_ITEM_NAME`)
  - Fields: `username` (email), `password`
  - One-time password (TOTP) configured

**Setup:**

1. Create a 1Password service account:
   ```bash
   # Follow: https://developer.1password.com/docs/service-accounts/get-started/
   ```

2. Grant the service account read access to the Deskbird item

3. Store the service account token in Kubernetes secret:
   ```bash
   kubectl create secret generic deskbird-credentials \
     --from-literal=OP_SERVICE_ACCOUNT_TOKEN="your-token-here" \
     --from-literal=OP_ITEM_NAME="Deskbird" \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

4. The script will automatically fetch fresh credentials and OTP codes at runtime

## Deployment

### Using Kustomize (Recommended)

1. Create and encrypt your secret:
   ```bash
   cd k8s/overlays/prod
   # Edit secret.yaml with your 1Password service account token
   # Encrypt the secret with your preferred tool (e.g., SOPS, sealed-secrets)
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

2. Update `cronjob.yaml` with your image registry

3. Apply resources:
   ```bash
   kubectl apply -f secret.yaml
   kubectl apply -f cronjob.yaml
   ```

## Notes

- The OTP challenge may require 1Password integration or a TOTP solution
- Currently scheduled to run every Thursday at 8 AM UTC
- Adjust the schedule in `cronjob.yaml` as needed
- Screenshot saved to `/tmp/deskbird_error.png` on failure for debugging
