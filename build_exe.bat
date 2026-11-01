@echo off
rem Сборка EXE через PyInstaller. Запускать из корня проекта в активированном .venv.
rem Результат: dist\AstronomicalCalendar\AstronomicalCalendar.exe
pip install -r requirements-dev.txt || exit /b 1
pyinstaller --noconfirm --clean --windowed --name AstronomicalCalendar ^
  --collect-data skyfield --collect-data tzdata ^
  --add-data "config;config" --add-data "resources;resources" ^
  main.py || exit /b 1
echo.
echo Готово: dist\AstronomicalCalendar\AstronomicalCalendar.exe
