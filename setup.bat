@echo off
cd /d "%~dp0"
echo Criando ambiente virtual...
python -m venv venv || goto :erro
echo Instalando dependencias...
call venv\Scripts\python.exe -m pip install --upgrade pip
call venv\Scripts\python.exe -m pip install -r requirements.txt || goto :erro
echo.
echo Tudo pronto. Rode run.bat para abrir a interface.
pause
exit /b 0

:erro
echo.
echo Falhou. Confira se o Python 3.10+ esta instalado e no PATH.
pause
exit /b 1
