@echo off
chcp 65001 >nul
echo =========================================================
echo            ZEN70 V2.1 一键启动引擎 (Start Engine)
echo =========================================================

echo.
echo [1/4] 正在拉起底层基础网络与容器编排...
docker compose -p zen70 up -d

echo.
echo [2/4] 环境预检与探测...
set PYTHONPATH=.
set REDIS_HOST=127.0.0.1

echo.
echo [3/4] 正在拉起物理极刑安全探针(Sentinel)至后台静默运行...
start "ZEN70_Sentinel" /MIN python backend/sentinel/top_sentinel.py

echo.
echo [4/4] 正在呼出主控台浏览器窗口...
start http://localhost/
start http://localhost/board

echo.
echo =========================================================
echo ✅ ZEN70 系统已全栈满血上线！
echo =========================================================
pause
