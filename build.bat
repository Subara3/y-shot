@echo off
REM y-shot exe build
REM 初回のみ: pip install pyinstaller
py -m PyInstaller --onefile --noconsole --name y-shot --add-data "templates;templates" --collect-all flet --collect-all flet_desktop --collect-all selenium --collect-all openpyxl y_shot.py
echo.
echo ビルド完了: dist\y-shot.exe
pause
