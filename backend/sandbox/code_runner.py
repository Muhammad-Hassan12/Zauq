"""Hardened Code Execution Sandbox for Zauq v4.

Features:
- Global concurrency semaphore (SANDBOX_MAX_CONCURRENCY)
- Strict output truncation (SANDBOX_MAX_OUTPUT_CHARS)
- Unique execution ID & container naming (zauq_exec_<id>)
- Explicit container cleanup on timeout via 'docker rm -f'
- Security flags: --cap-drop ALL, --security-opt no-new-privileges, --network none,
  --memory 256m, --cpus 0.5, --pids-limit 50, --read-only, --user 65534:65534
- Image allowlist (python:3.11-slim, node:18-alpine, alpine:latest)
- Logging without code content exposure
"""

import os
import shutil
import asyncio
import tempfile
import time
import uuid
import logging
from typing import Dict, Any, Optional

from backend.config import settings

logger = logging.getLogger("zauq.sandbox")

_MAX_CODE_LENGTH = 50_000  # 50KB max code size

_ALLOWED_IMAGES = {
    "python": ("python:3.11-slim", "py", ["python3", "/sandbox/code.py"]),
    "javascript": ("node:18-alpine", "js", ["node", "/sandbox/code.js"]),
    "node": ("node:18-alpine", "js", ["node", "/sandbox/code.js"]),
    "js": ("node:18-alpine", "js", ["node", "/sandbox/code.js"]),
    "bash": ("alpine:latest", "sh", ["sh", "/sandbox/code.sh"]),
    "sh": ("alpine:latest", "sh", ["sh", "/sandbox/code.sh"]),
}

# Global concurrency lock across all requests on this host
_sandbox_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    global _sandbox_semaphore
    if _sandbox_semaphore is None:
        _sandbox_semaphore = asyncio.Semaphore(max(1, settings.SANDBOX_MAX_CONCURRENCY))
    return _sandbox_semaphore


def _find_docker_binary() -> str:
    found = shutil.which("docker")
    if found:
        return found
    for fallback in ("/usr/local/bin/docker", "/usr/bin/docker", "/bin/docker"):
        if os.path.isfile(fallback) and os.access(fallback, os.X_OK):
            return fallback
    return "docker"


async def is_docker_available() -> bool:
    """Checks if Docker daemon is running and reachable."""
    docker_bin = _find_docker_binary()
    if not shutil.which(docker_bin) and not (os.path.isabs(docker_bin) and os.path.isfile(docker_bin)):
        return False
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "ps",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=5.0)
        return proc.returncode == 0
    except Exception:
        return False
    finally:
        if proc is not None and proc.returncode is None:
            proc.kill()
            await proc.wait()


def _truncate_output(text: str, max_chars: int) -> tuple[str, bool]:
    """Truncate output if it exceeds max_chars."""
    if len(text) <= max_chars:
        return text, False
    trunc_msg = f"\n... [Output truncated at {max_chars:,} characters]"
    return (text[:max(0, max_chars-len(trunc_msg))] + trunc_msg)[:max_chars], True


async def _cleanup_container(container_name: str) -> None:
    """Forcefully remove a container if it is still running."""
    proc = None
    try:
        docker_bin = _find_docker_binary()
        proc = await asyncio.create_subprocess_exec(
            docker_bin, "rm", "-f", container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except Exception as e:
        logger.warning(f"Failed to cleanup container {container_name}: {e}")
    finally:
        if proc is not None and proc.returncode is None:
            proc.kill()
            await proc.wait()


async def execute_code_docker(
    code: str,
    language: str = "python",
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Execute code in a hardened Docker container under concurrency controls."""
    effective_timeout = min(30.0, max(0.1, float(timeout if timeout is not None else settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS)))
    exec_id = f"zauq_exec_{uuid.uuid4().hex[:12]}"
    max_output = settings.SANDBOX_MAX_OUTPUT_CHARS

    if len(code.encode('utf-8')) > _MAX_CODE_LENGTH:
        return {
            "execution_id": exec_id,
            "success": False,
            "stdout": "",
            "stderr": f"Code too large. Maximum allowed size is {_MAX_CODE_LENGTH:,} characters.",
            "exit_code": 1,
            "execution_time_ms": 0,
            "timed_out": False,
            "truncated": False,
        }

    lang = language.lower().strip()
    if lang not in _ALLOWED_IMAGES:
        return {
            "execution_id": exec_id,
            "success": False,
            "stdout": "",
            "stderr": f"Unsupported language '{language}'. Supported: python, javascript, bash",
            "exit_code": 1,
            "execution_time_ms": 0,
            "timed_out": False,
            "truncated": False,
        }

    image, ext, container_cmd = _ALLOWED_IMAGES[lang]

    semaphore = _get_semaphore()
    async with semaphore:
        tmp_dir = tempfile.mkdtemp(prefix="zauq_sandbox_", dir=settings.SANDBOX_SPOOL_DIR or None)
        code_file = os.path.join(tmp_dir, f"code.{ext}")
        proc = None

        try:
            with open(code_file, "w", encoding="utf-8") as f:
                f.write(code)
            os.chmod(code_file, 0o444)
            host_code_file = code_file
            if settings.SANDBOX_HOST_SPOOL_DIR:
                if not settings.SANDBOX_SPOOL_DIR or not os.path.isabs(settings.SANDBOX_HOST_SPOOL_DIR):
                    raise ValueError('Sandbox spool paths must be explicitly configured and absolute')
                host_code_file = os.path.join(settings.SANDBOX_HOST_SPOOL_DIR, os.path.basename(tmp_dir), f'code.{ext}')

            docker_bin = _find_docker_binary()
            docker_cmd = [
                docker_bin, "run", "--rm",
                "--name", exec_id,
                '--pull', 'never',
                '--log-driver', 'none',
                "--network", "none",
                "--memory", "256m",
                "--cpus", "0.5",
                "--pids-limit", "50",
                "--read-only",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "--user", "65534:65534",
                "--tmpfs", "/tmp:size=10m,noexec",
                "-v", f"{host_code_file}:/sandbox/code.{ext}:ro",
                image,
            ] + container_cmd

            start_time = time.time()
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                raw_stdout, raw_stderr, overflow = await asyncio.wait_for(
                    _capture_output(proc, max_output * 4),
                    timeout=effective_timeout,
                )
                duration_ms = int((time.time() - start_time) * 1000)

                stdout_decoded = raw_stdout.decode("utf-8", errors="replace")
                stderr_decoded = raw_stderr.decode("utf-8", errors="replace")

                stdout_clean, trunc_out = _truncate_output(stdout_decoded, max_output)
                stderr_clean, trunc_err = _truncate_output(stderr_decoded, max(0, max_output-len(stdout_clean)))

                success = proc.returncode == 0
                logger.info(
                    f"Sandbox exec={exec_id} lang={lang} duration_ms={duration_ms} "
                    f"exit_code={proc.returncode} success={success}"
                )

                return {
                    "execution_id": exec_id,
                    "success": success,
                    "stdout": stdout_clean,
                    "stderr": stderr_clean,
                    "exit_code": proc.returncode,
                    "execution_time_ms": duration_ms,
                    "timed_out": False,
                    "truncated": overflow or trunc_out or trunc_err,
                }

            except asyncio.TimeoutError:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.warning(f"Sandbox exec={exec_id} timed out after {effective_timeout}s. Force cleaning container.")
                await _terminate_execution(proc, exec_id)

                return {
                    "execution_id": exec_id,
                    "success": False,
                    "stdout": "",
                    "stderr": f"Execution timed out after {effective_timeout} seconds.",
                    "exit_code": -1,
                    "execution_time_ms": duration_ms,
                    "timed_out": True,
                    "truncated": False,
                }

        except asyncio.CancelledError:
            await asyncio.shield(_terminate_execution(proc, exec_id))
            raise
        except Exception as e:
            logger.error(f"Sandbox exec={exec_id} unexpected error: {e}")
            await _cleanup_container(exec_id)
            return {
                "execution_id": exec_id,
                "success": False,
                "stdout": "",
                "stderr": f"Docker execution error: {str(e)}",
                "exit_code": 1,
                "execution_time_ms": 0,
                "timed_out": False,
                "truncated": False,
            }
        finally:
            if proc is not None and proc.returncode is None:
                await asyncio.shield(_terminate_execution(proc, exec_id))
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass


import httpx


async def _terminate_execution(proc, container_name):
    if proc is not None:
        try:
            if proc.returncode is None:
                killed = proc.kill()
                if asyncio.iscoroutine(killed):
                    await killed
            await asyncio.wait_for(proc.wait(), 5)
        except Exception:
            pass
    await _cleanup_container(container_name)


async def _capture_output(proc, max_bytes):
    """Drain pipes in fixed chunks; retain at most one shared byte budget."""
    retained = 0
    overflow = False
    async def read(stream):
        nonlocal retained, overflow
        chunks = []
        while True:
            chunk = await stream.read(8192)
            if not chunk:
                break
            allowed = max(0, max_bytes - retained)
            if len(chunk) > allowed:
                overflow = True
            kept = chunk[:allowed]
            retained += len(kept)
            if kept:
                chunks.append(kept)
        return b''.join(chunks)
    stdout, stderr, _ = await asyncio.gather(read(proc.stdout), read(proc.stderr), proc.wait())
    return stdout, stderr, overflow


async def execute_code_via_runner(
    runner_url: str,
    code: str,
    language: str = "python",
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Delegate code execution to isolated HTTP sandbox runner."""
    endpoint = f"{runner_url.rstrip('/')}/execute"
    headers = {"Content-Type": "application/json"}
    if settings.INTERNAL_API_KEY:
        headers["X-Internal-Token"] = settings.INTERNAL_API_KEY

    effective_timeout = min(30.0, max(1.0, float(timeout if timeout is not None else settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS)))
    payload = {
        "code": code,
        "language": language,
        "timeout": effective_timeout,
    }

    req_timeout = effective_timeout + 10.0
    try:
        async with httpx.AsyncClient(timeout=req_timeout) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in (401, 403):
                return {
                    "execution_id": f"zauq_exec_{uuid.uuid4().hex[:12]}",
                    "success": False,
                    "stdout": "",
                    "stderr": "Sandbox runner authentication failed.",
                    "exit_code": 1,
                    "execution_time_ms": 0,
                    "timed_out": False,
                    "truncated": False,
                }
            else:
                return {
                    "execution_id": f"zauq_exec_{uuid.uuid4().hex[:12]}",
                    "success": False,
                    "stdout": "",
                    "stderr": f"Sandbox runner error (HTTP {resp.status_code}).",
                    "exit_code": 1,
                    "execution_time_ms": 0,
                    "timed_out": False,
                    "truncated": False,
                }
    except Exception as exc:
        logger.error(f"Failed to communicate with sandbox runner at '{runner_url}': {exc}")
        return {
            "execution_id": f"zauq_exec_{uuid.uuid4().hex[:12]}",
            "success": False,
            "stdout": "",
            "stderr": "Failed to communicate with sandbox runner.",
            "exit_code": 1,
            "execution_time_ms": 0,
            "timed_out": False,
            "truncated": False,
        }


async def execute_code(
    code: str,
    language: str = "python",
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Top-level entrypoint for sandbox execution."""
    runner_url = getattr(settings, "SANDBOX_RUNNER_URL", "") or os.environ.get("SANDBOX_RUNNER_URL", "")
    if runner_url:
        return await execute_code_via_runner(runner_url, code, language, timeout)
    elif await is_docker_available():
        return await execute_code_docker(code, language, timeout)
    else:
        return {
            "execution_id": f"zauq_exec_{uuid.uuid4().hex[:12]}",
            "success": False,
            "stdout": "",
            "stderr": "Code execution failed: Docker sandbox is not available on the host system. For security, direct host execution is disabled.",
            "exit_code": 1,
            "execution_time_ms": 0,
            "timed_out": False,
            "truncated": False,
        }


async def get_sandbox_status() -> Dict[str, Any]:
    """Returns sandbox health, limits, and runtime configuration."""
    runner_url = getattr(settings, "SANDBOX_RUNNER_URL", "") or os.environ.get("SANDBOX_RUNNER_URL", "")
    if runner_url:
        try:
            endpoint = f"{runner_url.rstrip('/')}/status"
            headers = {}
            if settings.INTERNAL_API_KEY:
                headers["X-Internal-Token"] = settings.INTERNAL_API_KEY
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(endpoint, headers=headers)
                if resp.status_code == 200:
                    status_data = resp.json()
                    status_data["isolated_runner"] = True
                    status_data["runner_url"] = runner_url
                    return status_data
        except Exception as e:
            logger.warning(f"Could not reach sandbox runner at {runner_url}: {e}")
            return {
                "status": "runner_unreachable",
                "docker_available": False,
                "isolated_runner": True,
                "runner_url": runner_url,
                "error": str(e),
            }

    docker_up = await is_docker_available()
    allowed_unique = sorted(list(set(img for img, _, _ in _ALLOWED_IMAGES.values())))
    return {
        "status": "ready" if docker_up else "docker_unavailable",
        "docker_available": docker_up,
        "max_concurrency": settings.SANDBOX_MAX_CONCURRENCY,
        "default_timeout_seconds": settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS,
        "max_output_chars": settings.SANDBOX_MAX_OUTPUT_CHARS,
        "auto_code_test_default": settings.AUTO_CODE_TEST_DEFAULT,
        "auto_code_repair_attempts": settings.AUTO_CODE_REPAIR_ATTEMPTS,
        "allowed_images": allowed_unique,
        "security": {
            "network": "none",
            "cap_drop": "ALL",
            "no_new_privileges": True,
            "read_only": True,
            "memory": "256m",
            "cpus": 0.5,
            "pids_limit": 50,
            "user": "65534:65534",
        },
    }
