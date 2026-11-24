# Project plan

## Included in prototype
- Dashboard summary cards
- Request creation form with demo client choices
- Request list and statuses
- Approve/reject actions
- Simulate/complete workflow actions
- Event history
- FastAPI API with SQLite persistence

## Next development steps
1. Add authenticated accounts and role-based server-side authorization.
2. Replace SQLite with PostgreSQL and migration tooling.
3. Build a dedicated mobile client (React Native) for client consent UX.
4. Add push notifications that contain no secrets.
5. Add tenant isolation and device registration/revocation.
6. Add automated unit, API, and security tests.
7. Conduct privacy and security review before any production deployment.

## Safe demo scope
The prototype does not process real SMS or authentication codes. Its simulated status transitions are for UI demonstration only.
