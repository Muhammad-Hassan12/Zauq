import sys
import os
import shutil
import asyncio
import tempfile
import time
from typing import Dict, Any

async def is_docker_available() -> bool:
    docker_path = shutil.which("docker")
    if not docker_path:
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "info",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await asyncio.wait_for(proc.wait(), timeout=2.0)
        return proc.returncode == 0
    except Exception:
        return False

async def execute_code_docker(code: str, language: str = "python", timeout: float = 5.0) -> Dict[str, Any]:
    lang_map = {
        "python": ("python:3.11-slim", ["python3", "-c", code]),
        "javascript": ("node:18-alpine", ["node", "-e", code]),
        "node": ("node:18-alpine", ["node", "-e", code]),
        "js": ("node:18-alpine", ["node", "-e", code]),
        "bash": ("alpine:latest", ["sh", "-c", code]),
        "sh": ("alpine:latest", ["sh", "-c", code])
    }

    lang = language.lower()
    if lang not in lang_map:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Unsupported language '{language}'. Supported: python, javascript, bash",
            "exit_code": 1,
            "execution_time_ms": 0
        }

    image, cmd = lang_map[lang]
    docker_cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--memory", "256m",
        "--cpus", "0.5",
        "--pids-limit", "50",
        image
    ] + cmd

    start_time = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "success": proc.returncode == 0,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode,
            "execution_time_ms": duration_ms
        }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution timed out after {timeout} seconds.",
            "exit_code": -1,
            "execution_time_ms": int(timeout * 1000)
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Docker execution error: {str(e)}",
            "exit_code": 1,
            "execution_time_ms": 0
        }

async def execute_code(code: str, language: str = "python", timeout: float = 5.0) -> Dict[str, Any]:
    if await is_docker_available():
        return await execute_code_docker(code, language, timeout)
    else:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Code execution failed: Docker sandbox is not available on the host system. For security, direct host execution is disabled.",
            "exit_code": 1,
            "execution_time_ms": 0
        }
