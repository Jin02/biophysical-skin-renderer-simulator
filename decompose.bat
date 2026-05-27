@echo off
REM Drag an image file onto this .bat (or run: decompose.bat IMAGE [Label] [--remove-shading])
REM It runs the v2 ICA decomposition and registers the result as a texture preset
REM for skin-renderer-v2.html.
setlocal
cd /d "%~dp0"

if "%~1"=="" (
  echo Usage: drag an image onto this file, or run:
  echo     decompose.bat IMAGE [Label] [--remove-shading]
  echo.
  echo   --remove-shading : use for photos with strong shading ^(not flat albedo^)
  pause
  exit /b 1
)

REM Pick a Python launcher
where py >nul 2>&1 && (set "PY=py -3") || (set "PY=python")

set "IMG=%~1"
set "LABEL=%~2"
if "%LABEL%"=="" set "LABEL=%~n1"

set "RS="
echo %*| find "--remove-shading" >nul && set "RS=--remove-shading"

echo Decomposing "%IMG%"  ->  preset "%LABEL%"
%PY% skin_decompose_v2.py add "%IMG%" "%LABEL%" skin_presets_v2 %RS%
echo.
echo Done. Refresh skin-renderer-v2.html  -- a Texture button "%LABEL%" was added.
pause
