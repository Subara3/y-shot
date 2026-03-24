@echo off
REM y-shot exe build script
REM 事前に: pip install pyinstaller

pyinstaller --onefile --windowed --name y-shot y_shot.py

echo.
echo ビルド完了: dist\y-shot.exe
pause
