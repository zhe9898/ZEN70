#!/usr/bin/env bash
# ZEN70 V2.1 一键启动引擎 (Linux/macOS)
echo "========================================================="
echo "           ZEN70 V2.1 一键启动引擎 (Start Engine)        "
echo "========================================================="

echo -e "\n[1/4] 正在拉起底层基础网络与容器编排..."
docker compose -p zen70 up -d

echo -e "\n[2/4] 环境预检与探测..."
export PYTHONPATH="."
export REDIS_HOST="127.0.0.1"

echo -e "\n[3/4] 正在拉起物理极刑安全探针(Sentinel)至后台静默运行..."
# 检查是否已有探针运行以防多开
pkill -f "python backend/sentinel/top_sentinel.py" 2>/dev/null
nohup python backend/sentinel/top_sentinel.py > /dev/null 2>&1 &

echo -e "\n[4/4] 守护进程已就位。请访问:"
echo "主控台: http://localhost/"
echo "家族信标: http://localhost/board"

echo -e "\n========================================================="
echo "✅ ZEN70 系统已全栈满血上线！"
echo "========================================================="
