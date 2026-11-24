# GST OTP Reader — local runnable demo

A **simulation-only** prototype for the GST OTP Reader workflow described in the technical specification. It does not read SMS, handle real OTPs, authenticate to the GST portal, or perform filing.


## Requirements
- Windows: Python 3.10+ (Python launcher `py`), Node.js LTS/npm
- macOS/Linux: Python 3.10+, Node.js LTS/npm

## Quick start (Windows)
1. Extract this folder.
2. Double-click `start_windows.bat`.
3. Wait for backend and frontend terminals to start.
4. Open http://localhost:5173
5. API documentation: http://localhost:8000/docs


## Quick start (macOS/Linux)
From this folder run:
```bash
./start_linux_mac.sh
```
Then open http://localhost:5173. API docs at http://localhost:8000/docs.


## Manual startup
Backend terminal:
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```
Frontend terminal:
```bash
cd frontend
npm install
npm run dev
```

## Demo flow
1. Create a demo request from the dashboard.
2. Use Approve or Reject.
3. Approved requests can be moved to Simulation.
4. Simulation can be marked Complete.
5. Cancel an active request if desired.

The demo uses SQLite (`backend/gst_demo.db`) and creates it automatically on first run.


## Safety and limitations
- Demo data only. Use masked GSTINs and dummy clients.
- No real OTP/SMS handling or automated GST portal login is implemented.
- The API is a local prototype without production authentication/authorization.
- Do not deploy publicly or use with real client data.
- Before production, implement reviewed authentication, tenant isolation, rate limiting, secrets management, monitoring, security testing, consent UX, and approved integrations.


## Project structure
```
gst-otp-reader/
  backend/app/main.py     FastAPI demo API
  backend/requirements.txt
  frontend/             React + Vite dashboard
  docs/PROJECT_PLAN.md
  start_windows.bat
  start_linux_mac.sh
```
