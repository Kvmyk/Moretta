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

:: Generowanie brakujących sekretów. Domyślna wartość oznaczałaby, że każda
:: instalacja ma ten sam klucz szyfrujący i to samo hasło administratora.
call :FillIfEmpty VAULT_ENCRYPTION_KEY
call :FillIfEmpty KEYCLOAK_ADMIN_PASSWORD

:: Odczyt wybranego modelu z .env
set MODEL=phi4-mini
for /f "tokens=1,2 delims==" %%A in ('findstr /B "LOCAL_MODEL=" .env 2^>nul') do (
    set MODEL=%%B
)

echo [INFO] Wybrany model lokalny do pobrania: !MODEL!

:: Uruchamianie kontenerów
echo [INFO] Uruchamianie kontenerów (docker compose up -d)...
docker compose up -d

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
echo Keycloak (SSO): http://localhost:3000/auth
echo.
echo Backend (8000), Keycloak (8080) i Ollama (11434) nasłuchują wyłącznie
echo na localhost i nie są dostępne z sieci.
echo Hasło administratora Keycloak znajdziesz w pliku .env
echo (zmienna KEYCLOAK_ADMIN_PASSWORD).
echo ==============================================
pause
exit /b 0

:: --- Uzupełnia zmienną w .env, jeśli jest pusta ---------------------------
:FillIfEmpty
set "KEYNAME=%~1"
set "CURVAL="
for /f "tokens=1,* delims==" %%A in ('findstr /B "%KEYNAME%=" .env 2^>nul') do (
    set "CURVAL=%%B"
)
if not "!CURVAL!"=="" goto :eof
for /f %%S in ('powershell -NoProfile -Command "[Convert]::ToBase64String((1..30 ^| ForEach-Object {Get-Random -Max 256})) -replace '[/+=]',''"') do (
    set "NEWVAL=%%S"
)
powershell -NoProfile -Command "(Get-Content .env) -replace '^%KEYNAME%=.*', '%KEYNAME%=!NEWVAL!' | Set-Content .env -Encoding UTF8"
echo [INFO] Wygenerowano %KEYNAME%.
goto :eof
