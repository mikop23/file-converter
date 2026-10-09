"""
내장 AI - Ollama 없이 프로그램 안에서 AI 돌리기
  엔진: llama.cpp의 llama-server (프로그램 bin/llama 폴더에 같이 들어 있음)
  모델: Qwen2.5-1.5B-Instruct (Apache-2.0, 약 1.1GB) → 처음 한 번 다운로드
"""
import os, socket, subprocess, sys, time, urllib.request, json
from pathlib import Path

import fconv

MODEL_NAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_URL = ("https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/" + MODEL_NAME)
MODEL_SIZE_MB = 1120
PORT = int(os.environ.get("FCONV_AI_PORT", "18080"))
API = f"http://127.0.0.1:{PORT}/v1/chat/completions"


def data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    d = Path(base) / "FileConverter"
    d.mkdir(parents=True, exist_ok=True)
    return d

def model_path():
    return data_dir() / "models" / MODEL_NAME

def has_model():
    return model_path().is_file()

def server_exe():
    for name in ("llama-server.exe", "llama-server"):
        p = fconv.APP_DIR / "bin" / "llama" / name
        if p.is_file():
            return p
    w = fconv.shutil.which("llama-server")
    return Path(w) if w else None

def available():
    """이 프로그램에 AI 엔진이 들어 있는지"""
    return server_exe() is not None


def download_model(progress=None, url=MODEL_URL):
    """이어받기 지원 다운로드. progress(받은MB, 전체MB)"""
    dst = model_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_suffix(".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        if have and r.status != 206:          # 서버가 이어받기 거부 → 처음부터
            have = 0
        total = have + int(r.headers.get("Content-Length") or 0)
        with open(part, "ab" if have else "wb") as f:
            got = have
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if progress:
                    progress(got / 1e6, total / 1e6 if total else MODEL_SIZE_MB)
    if total and part.stat().st_size < total:
        raise IOError("다운로드가 중간에 끊겼어요. 다시 누르면 이어서 받아요.")
    part.replace(dst)
    return dst


class Server:
    """llama-server 켜고 끄기"""
    def __init__(self):
        self.proc = None

    def running(self):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1) as r:
                return r.status == 200
        except Exception:
            return False

    def start(self, timeout=90):
        if self.running():
            return True
        exe = server_exe()
        if not exe or not has_model():
            return False
        with socket.socket() as s:                       # 포트 쓰는 중이면 실패 처리
            if s.connect_ex(("127.0.0.1", PORT)) == 0:
                return False
        threads = max(2, (os.cpu_count() or 4) // 2)
        self.proc = subprocess.Popen(
            [str(exe), "-m", str(model_path()), "--host", "127.0.0.1", "--port", str(PORT),
             "-c", "4096", "-t", str(threads), "--log-disable"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **fconv.NO_WINDOW)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                return False
            if self.running():
                return True
            time.sleep(0.5)
        return False

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except Exception:
                self.proc.kill()
        self.proc = None
