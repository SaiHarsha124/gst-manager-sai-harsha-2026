# GST OTP Reader

A **consent-based OTP coordination tool** for CA firms and their clients (per *Technical Development Specification*).
It is not an SMS-surveillance app, not an OTP database, and not a GST Portal login bot: the auditor always types the OTP into the official portal.

```
gst-otp-reader/
├─ backend/   FastAPI + PostgreSQL (SQLite for local dev) – workflow, authz, one-time relay, audit
│  ├─ app/    main.py (API+WS) · models.py · otp_store.py · hub.py · security.py · ratelimit.py · seed.py
│  └─ tests/  state machine, one-time delivery, tenant isolation, expiry, revocation, no-OTP-at-rest
├─ mobile/    React Native + TypeScript (Expo dev build) – CLIENT / AUDITOR / ADMIN in one app
└─ docker-compose.yml
```

## Run the backend
```bash
cd backend && pip install -r requirements.txt
python -m app.seed                      # demo data; password for all users: Demo@12345
uvicorn app.main:app --reload           # docs at http://localhost:8000/docs
pytest -q                               # run the test suite
# Postgres + API:  SECRET_KEY=$(openssl rand -hex 32) docker compose up --build
```
Demo logins: `admin@sharma.test`, `auditor@sharma.test`, `client@acme.test` (another tenant: `auditor@other.test`).

## Run the mobile app
```bash
cd mobile && npm install
EXPO_PUBLIC_API_URL=https://your-host npx expo run:android   # development build; Expo Go cannot load native SMS code
```

## Workflow (spec §5, §11)
`REQUESTED → CLIENT_NOTIFIED → CLIENT_APPROVED → WAITING_FOR_SMS → (OTP_DETECTED) → WAITING_FOR_SHARING_APPROVAL → OTP_AUTHORIZED → OTP_DELIVERED → PORTAL_VERIFIED`
with terminal `REJECTED / EXPIRED / FAILED / CANCELLED`. The filing ARN is recorded separately (`POST …/filing-arn`) and only after `PORTAL_VERIFIED`.

1. Auditor creates a request (client, GSTIN, return, period, purpose). Client is marked *notified* only once delivery is confirmed (live socket or the client fetching it).
2. Client approves on a **paired, non-revoked device** (`X-Device-Id`). Nothing is accepted before approval.
3. App optionally uses Google SMS User Consent; otherwise the client enters the OTP. It is held **in server memory only**.
4. Client gives a **separate** explicit confirmation (`authorize-share` with `confirm:true`).
5. Assigned auditor calls `GET …/otp` once; it is popped from memory (`Cache-Control: no-store`). Second call → 409.
6. Auditor enters the OTP in the official portal and records the real result.

## Spec requirement → where implemented
| Requirement | Implementation |
|---|---|
| No OTP/SMS in DB, logs, audit, events | no OTP column; `otp_store.py` memory-only; `audit()` rejects secret keys; WS payloads status-only; test scans the DB file |
| Tenant isolation | `organization_id` on every query; `load()` returns 404 and logs `SECURITY_CROSS_TENANT_ATTEMPT` |
| Client must approve + separately authorize | `approve`, `authorize-share` (state machine blocks skipping) |
| Bound to one auditor, one time, expiring | `otp_store.pop(session, auditor_id)`, TTL = session expiry, background + lazy expiry |
| Short-lived auth, rotation, revocation | 15-min JWT tied to a server session; refresh rotation with reuse detection; logout/device revoke kill sessions |
| Append-only audit | ORM guard blocks update/delete of `otp_audit_logs` |
| Rate limiting | login and request-creation limiters (`ratelimit.py`) |
| Delivered ≠ verified ≠ filed | separate statuses + `filing_arn` |

## Native SMS bridge (Phase 4 — to be completed on real devices)
`mobile/src/sms.ts` expects `NativeModules.SmsUserConsent` with `start(senderFilter): Promise<string|null>` and `stop()`, wrapping Google's **SMS User Consent API** (`SmsRetriever.startSmsUserConsent` + the consent `Intent`). Use a maintained React Native module after verifying it on your target Android devices, or write a minimal Kotlin bridge. Until it is added the app uses **manual entry**, which is the primary path (spec §18). Do not promise automatic reading: SMS format, Android version and device settings affect it.

## Notes and deviations
- `users.client_id` was added so a CLIENT login maps to its client record; `filing_arn` was added to `otp_sessions`.
- The OTP relay is in-process memory. If you run several API workers, use sticky routing per session (never store the OTP in a database/Redis persistence).
- Production: TLS termination (HTTPS/WSS) at a reverse proxy, secrets from a vault, set `SECRET_KEY`, add push notifications (status text only, never the OTP).
- The existing GST Filing Dashboard integrates by calling `POST /api/otp/sessions` with the selected client, GSTIN, return type and period.
