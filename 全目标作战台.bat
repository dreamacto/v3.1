@echo off
rem Compatibility wrapper; canonical launcher lives in launchers with the same file name.
call "%~dp0launchers\%~n0.bat" %*
exit /b %ERRORLEVEL%
