# GST Manager & Advanced GST OTP Application

A combined repository containing two independent GST-related applications built with modern web technologies.

## Applications

### 1. GST Manager
A web-based GST management application with:
- Admin login and dashboard
- Client management
- GST-related records and history
- GSTIN format validation
- Backend API built with FastAPI
- React frontend

**Default local addresses:**
- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- API documentation: http://localhost:8000/docs

### 2. Advanced GST OTP Reader
A simulation-only prototype demonstrating a GST OTP authorization workflow.

Features include:
- Admin, auditor and client demo roles
- Demo authorization requests
- Request approval and rejection
- Simulation workflow
- Request status tracking
- SQLite database
- FastAPI backend

**Default local addresses:**
- Backend: http://127.0.0.1:8001
- API documentation: http://127.0.0.1:8001/docs

**Important:** This application does not read SMS, process real OTPs, authenticate with the GST portal, or perform GST filing.

---

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI |
| Frontend | React, Vite |
| Database | SQLite |
| API | REST API |
| Authentication | Application-specific demo/admin authentication |

---

## Requirements

- Windows 10/11, macOS or Linux
- Python 3.10 or newer (Python 3.13 recommended for the advanced application)
- Node.js LTS and npm
- Git

---

## Project Structure

```text
gst-otp-reader/
│
├── backend/
│   ├── app/
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   ├── package.json
│   └── package-lock.json
│
├── gst-otp-reader/
│   ├── backend/
│   ├── mobile/
│   └── README.md
│
├── docs/
│   └── PROJECT_PLAN.md
│
├── start_windows.bat
├── start_linux_mac.sh
└── README.md
```

---

## Running GST Manager

### Backend

Open PowerShell:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Configure the required environment variables using your local `.env` file.

Start the backend:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

Open another PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Open:

http://localhost:5173

---

## Running Advanced GST OTP Reader

Open PowerShell:

```powershell
cd gst-otp-reader/backend
py -3.13 -m venv .venv313
.venv313\Scripts\Activate.ps1
pip install -r requirements.txt
```

Start the backend:

```powershell
python -m uvicorn app.main:app --reload --port 8001
```

Open another terminal for the mobile application setup if required. Follow the instructions in the nested `gst-otp-reader/README.md`.

API documentation:

http://127.0.0.1:8001/docs

---

## Database

Both applications use SQLite for local development.

Database files are generated locally and should not be committed to GitHub.

---

## Security and Limitations

- Use dummy data for testing.
- Never commit passwords, API keys, tokens, private certificates or `.env` files.
- Configure strong secrets and passwords before use.
- The Advanced GST OTP application is a simulation prototype.
- GSTIN format validation does not confirm registration status with the GST portal.
- Neither application should be treated as a production-ready GST filing or portal integration system without further development, security review and approved integrations.

---

## Development Status

This repository contains two independent development projects. Features and setup requirements may evolve as development continues.

## License

No open-source license has been specified yet. All rights are reserved by the repository owner unless a license is added.