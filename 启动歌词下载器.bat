@echo off
chcp 65001 >nul
cd /d "%~dp0"
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw lrc_gui.py
) else (
    where pyw >nul 2>&1
    if %errorlevel%==0 (
        start "" pyw -3 lrc_gui.py
    ) else (
        start "" python lrc_gui.py
    )
)
exit
