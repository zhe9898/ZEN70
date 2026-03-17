#!/usr/bin/env python3
import os
import sys
import subprocess

# 确保依赖环境
def ensure_dependencies():
    packages = ["fastapi", "uvicorn", "pyyaml", "pydantic", "ruamel.yaml"]
    try:
        import fastapi
        import uvicorn
        import yaml
        import pydantic
        from ruamel.yaml import YAML
    except ImportError:
        print("未检测到图形化部署引火器所需的轻量依赖，正在自动获取 (FastAPI/Uvicorn/PyYAML/Pydantic)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *packages])
        print("依赖拉取完毕！")

print("\n" + "="*50)
print("[*] 正在拉起 ZEN70 V2.0 图形化部署引擎...")
print("="*50 + "\n")

def find_free_port(start_port=8080, max_port=8099):
    import socket
    for port in range(start_port, max_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port

if __name__ == "__main__":
    # 将项目根目录加入到 sys.path
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.append(project_root)
    
    import uvicorn
    try:
        free_port = find_free_port()
        print(f"[>] 服务已预检启动，请在您的浏览器中访问: http://127.0.0.1:{free_port}\n")
        uvicorn.run("installer.main:app", host="127.0.0.1", port=free_port, log_level="info")
    except (Exception, SystemExit) as e:
        print(f"\n[致命错误] 图形向导启动失败: {e}")
        print("💡 可能是系统网络栈异常或端口均被占用。")
        input("\n按回车键退出，防止窗口闪退...")


