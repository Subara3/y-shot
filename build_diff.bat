@echo off
REM y-diff exe build
py -m PyInstaller --onefile --noconsole --name y-diff --icon=assets/diff_icon.ico --add-data "assets;assets" --collect-all flet --collect-all flet_desktop y_diff.py
echo.
echo ビルド完了: dist\y-diff.exe
pause
