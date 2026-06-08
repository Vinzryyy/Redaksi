@echo off
echo Menjalankan Backend Flask + Frontend Next.js...
echo.

REM --- Start Backend ---
start "Flask API" cmd /k "cd /d %~dp0backend && venv\Scripts\activate && python app.py"

REM --- Start Frontend ---
start "Next.js" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Backend: http://localhost:5000
echo Frontend: http://localhost:3000
echo.
echo Dua window terminal baru sudah terbuka.
pause
