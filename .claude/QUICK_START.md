# Quick start (most-run commands)

```bash
# Sanity-check the script (no test suite exists)
python3 -m py_compile deskbird_booking.py

# Build the image locally
docker build -t deskbird-booking:local .

# Render / validate k8s manifests
kubectl kustomize k8s/overlays/prod

# Inspect the CronJob in-cluster (note the explicit context)
KUBECONFIG=~/.kube/firefly.yaml kubectl --context firefly -n automation get cronjob,jobs,pods

# Trigger a manual run and follow logs
kubectl --context firefly -n automation create job --from=cronjob/deskbird-booking deskbird-manual
kubectl --context firefly -n automation logs -f job/deskbird-manual

# Deploy (normally Flux does this on release; manual only if needed)
kubectl apply -k k8s/overlays/prod

# Docs (Material for MkDocs; dep: mkdocs-material)
mkdocs serve      # live preview at :8000
mkdocs build      # output -> ./site (gitignored)
```
