@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ==============================================
echo Uruchamianie środowiska Moretta...
echo ==============================================

:: Sprawdzanie czy docker jest dostepny
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [BŁĄD] Docker nie jest dostępny.
    echo Upewnij się, że Docker Desktop jest uruchomiony.
    pause
    exit /b 1
)

:: Tworzenie .env z .env.example jesli nie istnieje
if not exist .env (
    echo [INFO] Tworzenie pliku .env na podstawie .env.example...
    copy .env.example .env >nul
)

:: Odczyt wybranego modelu z .env
set MODEL=phi4-mini
for /f "tokens=1,2 delims==" %%A in ('findstr /B "LOCAL_MODEL=" .env 2^>nul') do (
    set MODEL=%%B
)

echo [INFO] Wybrany model lokalny do pobrania: !MODEL!

:: Uruchamianie kontenerów
echo [INFO] Uruchamianie kontenerów (docker-compose up -d)...
docker-compose up -d

:: Oczekiwanie na start Ollamy
echo [INFO] Oczekiwanie na start serwisu Ollama (10 sekund)...
timeout /t 10 /nobreak >nul

:: Pobieranie modelu
echo [INFO] Rozpoczynam pobieranie modelu !MODEL! wewnątrz kontenera...
docker exec privateproxy-ollama ollama pull !MODEL!
if %errorlevel% neq 0 (
    echo [BŁĄD] Wystąpił problem podczas pobierania modelu. Zobacz wyżej.
) else (
    echo [SUKCES] Model pobrany!
)

echo.
echo ==============================================
echo [SUKCES] Środowisko zostało uruchomione!
echo Interfejs użytkownika (Frontend): http://localhost:3000
echo API (Backend): http://localhost:8000
echo Keycloak (SSO): http://localhost:3000/auth
echo ==============================================
pause
