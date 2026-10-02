@echo off
REM ============================================================================
REM  build_exe.bat
REM  Compila SynchMag.py a SynchMag.exe usando PyInstaller.
REM
REM  Requisitos:
REM    - Tener activado el entorno Conda donde instalaste pandas, gpxpy y
REM      geopandas (el mismo que usaste hasta ahora).
REM    - Este .bat instala PyInstaller si todavia no lo tenes.
REM
REM  Uso:
REM    1. Activa tu entorno:   conda activate NOMBRE_DE_TU_ENTORNO
REM    2. Corre este archivo haciendo doble click, o desde la consola:
REM         build_exe.bat
REM    3. Al terminar, el ejecutable queda en la carpeta "dist\SynchMag.exe"
REM ============================================================================

echo Instalando dependencias adicionales (matplotlib, PyInstaller)...
python -m pip install matplotlib pyinstaller --quiet

echo.
echo Compilando SynchMag.exe ...
python -m PyInstaller --onefile --console --name SynchMag SynchMag.py

echo.
if exist dist\SynchMag.exe (
    echo ============================================================
    echo  LISTO: el ejecutable quedo en dist\SynchMag.exe
    echo  Copialo junto a una carpeta "input" y ya podes usarlo.
    echo ============================================================
) else (
    echo ============================================================
    echo  Algo fallo. Revisa los mensajes de arriba.
    echo ============================================================
)

pause
