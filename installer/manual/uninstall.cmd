@echo off
chcp 65001 >nul
setlocal

rem BobrovMenu: removes the per-user installation made by install.cmd.
rem Only BobrovMenu.bundle is removed.

set "TARGET=%APPDATA%\Autodesk\ApplicationPlugins\BobrovMenu.bundle"
if not exist "%TARGET%" (
    echo BobrovMenu не установлен: %TARGET%
    pause
    exit /b 0
)

rmdir /s /q "%TARGET%"
if exist "%TARGET%" (
    echo Не удалось удалить %TARGET%. Закройте AutoCAD и запустите uninstall.cmd снова.
    pause
    exit /b 1
)

echo Удалено: %TARGET%
echo При следующем запуске AutoCAD элементы меню Bobrov исчезнут.
echo Команды установленных отдельно плагинов доступны из командной строки.
pause
exit /b 0
