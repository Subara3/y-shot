@echo off
REM y-shot exe build
REM templates/ フォルダをexeに同梱します
flet pack y_shot.py --name y-shot --add-data "templates;templates"
echo.
echo ビルド完了: dist\y-shot.exe
echo templates/ フォルダはexeに同梱されています
pause
