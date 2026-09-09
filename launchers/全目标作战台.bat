@echo off
chcp 65001 >nul
setlocal

set "PROJECT=D:\PythonSource\PythonProjects\PythonProject4"
set "PY=%PROJECT%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=D:\Desktop\天狐渗透工具箱-社区版V3.0+4.0更新升级包\天狐渗透工具箱-社区版V3.0\python3\python.exe"
if not exist "%PY%" set "PY=python"
echo Using Python: %PY%
echo.
rem Board: read-only aggregation of engagement cursors, operator tasks, ledger and run states.
rem This BAT passes all args through to scripts\reporting\engagement_board.py, e.g.:
rem   (no args) = board    --tasks    --runs N    --focus NAME    --handoff NAME [--stream wz|xcx]    --submit NAME    --assets    --json
rem --write variants land in engagements\_BOARD.md, engagements\_TASKS.md or the target logs dir.

"%PY%" "%PROJECT%\scripts\reporting\engagement_board.py" --write %*
echo.
pause
