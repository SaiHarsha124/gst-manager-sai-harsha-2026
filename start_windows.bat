@echo off
setlocal
cd /d "%~dp0"
if not exist backend\.venv (
  echo Creating Python environment...
  py -3 -m venv backend\.venv
)
echo Installing backend dependencies...
call backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
start "GST OTP Reader API" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
if not exist frontend\node_modules (
  echo Installing frontend dependencies...
  cd frontend && npm install && cd ..
)
start "GST OTP Reader UI" cmd /k "cd /d %~dp0frontend && npm run dev"
echo.
echo Started. API docs: http://localhost:8000/docs
 echo Frontend: check Vite terminal for its URL (normally http://localhost:5173)
endlocal
