@echo off
rem Construit la version portable dans dist\Buvette3000\
rem Les données (dist\Buvette3000\data) sont conservées d'une construction à l'autre.
setlocal
cd /d "%~dp0"

if not exist .venv (
    python -m venv .venv || goto :erreur
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip pyinstaller || goto :erreur

if exist dist\Buvette3000\data (
    if exist _data_sauvegarde rmdir /s /q _data_sauvegarde
    xcopy /e /i /q /y dist\Buvette3000\data _data_sauvegarde >nul || goto :erreur
)

pyinstaller --noconfirm --clean --onedir --windowed --name Buvette3000 --icon assets\buvette.ico --add-data "assets\buvette.ico;assets" --add-data "assets\logo_*.png;assets" buvette.py || goto :restaurer

:restaurer
if exist _data_sauvegarde (
    xcopy /e /i /q /y _data_sauvegarde dist\Buvette3000\data >nul
    rmdir /s /q _data_sauvegarde
)
if not exist dist\Buvette3000\Buvette3000.exe goto :erreur

echo.
echo OK : copier le dossier dist\Buvette3000 sur l'autre PC et lancer Buvette3000.exe
exit /b 0

:erreur
echo ECHEC de la construction.
exit /b 1
