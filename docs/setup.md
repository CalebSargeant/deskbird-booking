# Setup & Deployment

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

## Local run

```bash
python3 -m py_compile deskbird_booking.py   # sanity check (no test suite)
docker build -t deskbird-booking:local .

docker run --rm \
  -e OP_SERVICE_ACCOUNT_TOKEN="$OP_SERVICE_ACCOUNT_TOKEN" \
  -e OP_ITEM_NAME="Microsoft" -e OP_VAULT="<vault>" \
  -e OFFICE_ID="<id>" -e FLOOR_ID="<id>" -e PREFERRED_DESK="5.09 D" \
  deskbird-booking:local
```

Debug screenshots are written to `/tmp/deskbird_*.png` inside the container.

## Kubernetes

The prod overlay composes the CronJob with a SOPS/age-encrypted secret.

```bash
kubectl kustomize k8s/overlays/prod          # render/validate
kubectl apply -k k8s/overlays/prod           # manual deploy (Flux usually does this)

# Inspect (note the explicit context — the kubeconfig's current-context is stale)
KUBECONFIG=~/.kube/firefly.yaml kubectl --context firefly -n automation \
  get cronjob,jobs,pods
```

The secret is encrypted with SOPS + age (`k8s/overlays/prod/.sops.yaml`). Edit the
decrypted form with `sops k8s/overlays/prod/secret.enc.yaml`; **never commit a
plaintext `secret.yaml`** (it is gitignored).

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

## Docs

```bash
pip install mkdocs-material
mkdocs serve     # preview at http://127.0.0.1:8000
mkdocs build     # static site -> ./site (gitignored)
```
