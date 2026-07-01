# Common mistakes / gotchas

- **kubeconfig context is stale.** `~/.kube/firefly.yaml`'s current-context
  points at a non-existent EKS context. Always pass `--context firefly`
  (or `ember`), e.g. `KUBECONFIG=~/.kube/firefly.yaml kubectl --context firefly ...`.
- **Auth-complete check is load-bearing.** `is_authenticated_url()` must wait
  until the browser leaves `/sign-in`, `/login`, and `/authenticationHandler`.
  Loosening it (e.g. "just check for 'login'") re-breaks every run — the script
  navigates before Deskbird finishes the OAuth callback and gets bounced back.
- **Deskbird UI is data-testid driven and changes.** Booking uses
  `booking-suggestions-quick-book` / `booking-suggestions-card`;
  already-booked uses `booking-card-location`. If booking breaks, re-inspect
  the live DOM before editing selectors.
- **Script runs at import, needs env.** No `main()`. `OFFICE_ID` + `FLOOR_ID`
  must be set or it raises immediately. `PREFERRED_DESK` is optional and must be
  injected via the CronJob env (it lives in the secret).
- **No tests / no linter.** Don't assume pytest/ruff. Sanity-check with
  `python3 -m py_compile deskbird_booking.py`.
- **Secrets:** `secret.enc.yaml` is SOPS/age-encrypted; never commit a plaintext
  `secret.yaml`. Prod deploys via Flux — avoid manual `kubectl apply` to prod.
- **pre-commit** strips AI co-author trailers and pins GH Actions SHAs; expect it
  to rewrite commits.
