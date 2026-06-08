@echo off
echo ============================================
echo   Setup Aplikasi Berita
echo ============================================
echo.

REM --- Backend ---
echo [1/4] Membuat virtual environment Python...
cd /d "%~dp0backend"
python -m venv venv
call venv\Scripts\activate

echo [2/4] Install dependencies Python (Flask, psycopg2)...
pip install -r requirements.txt
echo.

REM --- Frontend ---
echo [3/4] Install dependencies Next.js...
cd /d "%~dp0frontend"
call npm install
echo.

REM --- Database ---
echo [4/4] Membuat database dan tabel...
echo Pastikan PostgreSQL sudah berjalan!
set PGPASSWORD=postgres
psql -U postgres -c "CREATE DATABASE berita_db;" 2>nul
psql -U postgres -d berita_db -f "%~dp0backend\schema.sql"
echo.

echo ============================================
echo   Setup selesai!
echo.
echo   Jalankan backend:
echo     cd backend
echo     venv\Scripts\activate
echo     python app.py
echo.
echo   Jalankan frontend (terminal baru):
echo     cd frontend
echo     npm run dev
echo.
echo   Buka http://localhost:3000
echo ============================================
pause
