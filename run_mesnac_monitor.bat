@echo off
title MESNAC Tyre Weight Live OPC UA Monitor
color 0A
cd /d "%~dp0"

echo ====================================================================
echo   PROMETEON TYRE GROUP - MESNAC TYRE WEIGHT LIVE MONITOR
echo ====================================================================
echo.
echo Select Target Building Machine:
echo   [1] MESNAC 1 (MESNAC26)
echo   [2] MESNAC 2 (MESNAC27)
echo   [3] Both Machines (MESNAC 1 and MESNAC 2)
echo.
set /p MCHOICE="Enter Choice (1, 2, or 3) [Default 1]: "

if "%MCHOICE%"=="2" (
    set MACHINE_ARG=--machine 2
) else if "%MCHOICE%"=="3" (
    set MACHINE_ARG=--machine both
) else (
    set MACHINE_ARG=--machine 1
)

echo.
echo Starting OPC UA Monitor (100ms scan rate)...
echo.

IF EXIST "python_portable\python.exe" (
    python_portable\python.exe mesnac_opcua_weight_monitor.py %MACHINE_ARG%
) ELSE (
    python mesnac_opcua_weight_monitor.py %MACHINE_ARG%
)

pause
