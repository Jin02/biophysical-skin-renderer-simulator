@echo off
REM Double-click to open the widget in your browser (it needs a tiny local server).
setlocal
cd /d "%~dp0"
where py >nul 2>&1 && (set "PY=py -3") || (set "PY=python")
start "skin-renderer server" %PY% -m http.server 8123
timeout /t 2 >nul
start "" "http://localhost:8123/skin-renderer-v2.html"
echo The widget should open in your browser.
echo (A separate black window is the server - keep it open while using the widget,
echo  close it when you're done. If the page didn't load, just refresh it.)
