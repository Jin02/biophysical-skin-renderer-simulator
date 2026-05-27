@echo off
REM Double-click this once to install the libraries the tool needs (numpy, pillow).
setlocal
cd /d "%~dp0"
where py >nul 2>&1 && (set "PY=py -3") || (set "PY=python")
echo Installing required libraries (numpy, pillow)...
echo.
%PY% -m pip install -r requirements.txt
echo.
echo ---------------------------------------------------------
echo Done. Now you can drag a face photo onto  decompose.bat
echo ---------------------------------------------------------
pause
