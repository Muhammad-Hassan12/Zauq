import sys
import os
import shutil
import asyncio
import tempfile
import time
from typing import Dict, Any

_MAX_CODE_LENGTH = 50_000  # 50KB max code size


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
    # Enforce code size limit
    if len(code) > _MAX_CODE_LENGTH:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Code too large. Maximum allowed size is {_MAX_CODE_LENGTH:,} characters.",
            "exit_code": 1,
            "execution_time_ms": 0
        }

    lang_map = {
        "python": ("python:3.11-slim", "py"),
        "javascript": ("node:18-alpine", "js"),
        "node": ("node:18-alpine", "js"),
        "js": ("node:18-alpine", "js"),
        "bash": ("alpine:latest", "sh"),
        "sh": ("alpine:latest", "sh")
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

    image, ext = lang_map[lang]

    # Write code to a temp file and mount it read-only — avoids shell metacharacter injection via -c flag
    tmp_dir = tempfile.mkdtemp(prefix="zauq_sandbox_")
    code_file = os.path.join(tmp_dir, f"code.{ext}")
    try:
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(code)

        # Build the interpreter command based on language
        if lang in ("python",):
            container_cmd = ["python3", "/sandbox/code.py"]
        elif lang in ("javascript", "node", "js"):
            container_cmd = ["node", "/sandbox/code.js"]
        else:
            container_cmd = ["sh", "/sandbox/code.sh"]

        docker_cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", "256m",
            "--cpus", "0.5",
            "--pids-limit", "50",
            "--read-only",
            "--user", "65534:65534",
            "--security-opt", "no-new-privileges",
            "--tmpfs", "/tmp:size=10m,noexec",
            "-v", f"{code_file}:/sandbox/code.{ext}:ro",
            image
        ] + container_cmd

        start_time = time.time()
        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
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
            # Explicitly kill the subprocess to avoid zombie containers
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
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
    finally:
        # Always clean up the temp directory
        try:
            import shutil as _shutil
            _shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


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
