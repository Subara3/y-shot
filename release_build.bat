@echo off
REM y-shot 配布パッケージ作成
REM 使い方: release_build.bat

echo === y-shot 配布パッケージ作成 ===

REM ビルド
echo [1/3] ビルド中...
py -m PyInstaller y-shot.spec --noconfirm
if errorlevel 1 (echo ビルド失敗 & pause & exit /b 1)

REM リリースフォルダ作成
echo [2/3] パッケージ作成中...
if exist release\y-shot rd /s /q release\y-shot
mkdir release\y-shot
mkdir release\y-shot\templates
mkdir release\y-shot\docs

copy dist\y-shot.exe release\y-shot\
copy dist\y-diff.exe release\y-shot\
copy templates\入力チェック_基本.csv release\y-shot\templates\
copy docs\y-shot_manual.docx release\y-shot\docs\
copy docs\wine_search_sample.yshot.json release\y-shot\
copy docs\partner_sample.yshot.json release\y-shot\

REM ZIP作成
echo [3/3] ZIP作成中...
if exist release\y-shot_v2.1.zip del release\y-shot_v2.1.zip
powershell -Command "Compress-Archive -Path 'release\y-shot' -DestinationPath 'release\y-shot_v2.1.zip'"

echo.
echo === 完了: release\y-shot_v2.1.zip ===
pause
