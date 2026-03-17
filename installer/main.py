import asyncio
import io
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

app = FastAPI(title="ZEN70 Web Installer API")

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_HTML = Path(__file__).resolve().parent / "index.html"
BOOTSTRAP_SCRIPT = ROOT_DIR / "scripts" / "bootstrap.py"
COMPILER_SCRIPT = ROOT_DIR / "scripts" / "compiler.py"
SYSTEM_YAML = ROOT_DIR / "system.yaml"
ENV_FILE = ROOT_DIR / ".env"


def patch_system_yaml_paths(media_path: str, models_path: str) -> bool:
    """路径解耦：仅修改路径相关键，保留 system.yaml 注释与格式（ruamel.yaml 回写）。"""
    if not SYSTEM_YAML.exists():
        return False
    try:
        from ruamel.yaml import YAML
        yaml_loader = YAML()
        yaml_loader.preserve_quotes = True
        data = yaml_loader.load(SYSTEM_YAML.read_text(encoding="utf-8"))
        if data is None:
            data = {}
        media = (media_path or "/mnt/media").strip() or "/mnt/media"
        models = (models_path or "/mnt/models").strip() or "/mnt/models"

        if "capabilities" not in data:
            data["capabilities"] = {}
        if "storage" not in data["capabilities"]:
            data["capabilities"]["storage"] = {}
        data["capabilities"]["storage"]["media_path"] = media

        if "sentinel" not in data:
            data["sentinel"] = {}
        mp = data["sentinel"].get("mount_container_map")
        if mp is None:
            data["sentinel"]["mount_container_map"] = {media: "zen70-jellyfin", "/mnt/cctv": "zen70-frigate"}
        else:
            if "/mnt/media" in mp:
                del mp["/mnt/media"]
            mp[media] = "zen70-jellyfin"
            if "/mnt/cctv" not in mp:
                mp["/mnt/cctv"] = "zen70-frigate"

        wt = data["sentinel"].get("watch_targets")
        if wt is None:
            data["sentinel"]["watch_targets"] = {"media_engine": [media, None, 1], "ai_vision": [models, None, 1]}
        else:
            wt["media_engine"] = [media, None, 1]
            wt["ai_vision"] = [models, None, 1]

        buf = io.StringIO()
        yaml_loader.dump(data, buf)
        SYSTEM_YAML.write_text(buf.getvalue(), encoding="utf-8")
        return True
    except Exception:
        try:
            import yaml
            data = yaml.safe_load(SYSTEM_YAML.read_text(encoding="utf-8")) or {}
            media = (media_path or "/mnt/media").strip() or "/mnt/media"
            models = (models_path or "/mnt/models").strip() or "/mnt/models"
            data.setdefault("capabilities", {}).setdefault("storage", {})["media_path"] = media
            data.setdefault("sentinel", {})
            mp = data["sentinel"].get("mount_container_map") or {}
            new_map = {k: v for k, v in mp.items() if k != "/mnt/media"}
            new_map[media] = mp.get("/mnt/media", "zen70-jellyfin")
            new_map.setdefault("/mnt/cctv", "zen70-frigate")
            data["sentinel"]["mount_container_map"] = new_map
            wt = data["sentinel"].get("watch_targets") or {}
            data["sentinel"]["watch_targets"] = {
                "media_engine": [media, None, 1],
                "ai_vision": [models, None, 1],
                **{k: v for k, v in wt.items() if k not in ("media_engine", "ai_vision")},
            }
            SYSTEM_YAML.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False), encoding="utf-8")
            return True
        except Exception:
            return False


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    if not FRONTEND_HTML.exists():
        return "Installer UI not found."
    return FRONTEND_HTML.read_text(encoding="utf-8")


@app.get("/api/logs")
async def stream_logs(
    domain: str = "home.zen70.local",
    tunnel_token: str = "",
    media_path: str = "/mnt/media",
    models_path: str = "/mnt/models",
):
    async def log_generator():
        env = os.environ.copy()
        if domain and domain != "home.zen70.local":
            env["ZEN70_DOMAIN"] = domain

        if tunnel_token and ENV_FILE.exists():
            content = ENV_FILE.read_text(encoding="utf-8")
            if "your_cloudflare_token_here_replace_me" in content:
                content = content.replace("your_cloudflare_token_here_replace_me", tunnel_token, 1)
                ENV_FILE.write_text(content, encoding="utf-8")
                yield "data: [installer] Written Cloudflare Tunnel Token to .env\n\n"

        media_path_clean = (media_path or "").strip() or "/mnt/media"
        models_path_clean = (models_path or "").strip() or "/mnt/models"
        if SYSTEM_YAML.exists():
            if patch_system_yaml_paths(media_path_clean, models_path_clean):
                yield f"data: [installer] 已写入路径解耦配置: MEDIA_PATH={media_path_clean}, models_path={models_path_clean}\n\n"
            if COMPILER_SCRIPT.exists():
                yield "data: [installer] 运行配置编译器生成 .env...\n\n"
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, str(COMPILER_SCRIPT),
                    cwd=str(ROOT_DIR),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                out, _ = await proc.communicate()
                for line in out.decode("utf-8", errors="replace").strip().splitlines():
                    if line:
                        yield f"data: {line}\n\n"
                yield "data: [installer] 编译器完成\n\n"
        else:
            yield "data: [installer] WARNING: system.yaml not found at root. Will attempt to pull.\n\n"

        cmd = [sys.executable, str(BOOTSTRAP_SCRIPT)]
        yield f"data: [installer] Starting Bootstrap: {' '.join(cmd)}\n\n"

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(ROOT_DIR),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if decoded:
                yield f"data: {decoded}\n\n"

        await process.wait()
        yield f"data: [EOF] Process completed with exit code {process.returncode}\n\n"

    return StreamingResponse(log_generator(), media_type="text/event-stream")
