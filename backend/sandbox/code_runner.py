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

async def execute_code_process(code: str, language: str = "python", timeout: float = 5.0) -> Dict[str, Any]:
    lang = language.lower()
    start_time = time.time()

    with tempfile.TemporaryDirectory() as tmpdir:
        if lang == "python":
            filepath = os.path.join(tmpdir, "script.py")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
            cmd = [sys.executable, filepath]
        elif lang in ["javascript", "js", "node"]:
            node_path = shutil.which("node")
            if not node_path:
                return {"success": False, "stdout": "", "stderr": "Node.js runtime not found.", "exit_code": 1, "execution_time_ms": 0}
            filepath = os.path.join(tmpdir, "script.js")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
            cmd = [node_path, filepath]
        elif lang in ["bash", "sh"]:
            bash_path = shutil.which("bash") or shutil.which("sh")
            if not bash_path:
                return {"success": False, "stdout": "", "stderr": "Bash runtime not found.", "exit_code": 1, "execution_time_ms": 0}
            filepath = os.path.join(tmpdir, "script.sh")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
            cmd = [bash_path, filepath]
        else:
            return {"success": False, "stdout": "", "stderr": f"Unsupported language '{language}'", "exit_code": 1, "execution_time_ms": 0}

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
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
            return {"success": False, "stdout": "", "stderr": f"Execution timed out after {timeout} seconds.", "exit_code": -1, "execution_time_ms": int(timeout * 1000)}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": f"Subprocess error: {str(e)}", "exit_code": 1, "execution_time_ms": 0}

async def execute_code(code: str, language: str = "python", timeout: float = 5.0) -> Dict[str, Any]:
    if await is_docker_available():
        return await execute_code_docker(code, language, timeout)
    else:
        return await execute_code_process(code, language, timeout)
