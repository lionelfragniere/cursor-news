@echo off
setlocal
cd /d "%~dp0.."
call android\build_android_debug.cmd
