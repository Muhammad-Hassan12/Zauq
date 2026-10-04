"""Explicit Docker release gate; never pretends mocks are container execution."""
import asyncio
import os
import shutil
import subprocess

import pytest

from backend.sandbox.code_runner import execute_code_docker

pytestmark = pytest.mark.skipif(os.environ.get('ZAUQ_RUN_DOCKER_TESTS') != 'true', reason='Real Docker release gate requires explicit opt-in')


def containers():
    result = subprocess.run(['docker','ps','-aq','--filter','name=zauq_exec_'],capture_output=True,text=True,check=True)
    return set(result.stdout.split())


@pytest.mark.asyncio
async def test_real_code_mount_and_security_controls():
    assert shutil.which('docker'), 'Docker release gate requested but unavailable'
    result = await execute_code_docker("import os\nprint('mounted-code-ok')\nprint(os.getuid())",timeout=5)
    assert result['success'], result['stderr']
    assert 'mounted-code-ok' in result['stdout']
    assert '65534' in result['stdout']
    network = await execute_code_docker("import socket\nsocket.create_connection(('1.1.1.1',443),timeout=1)",timeout=5)
    assert not network['success']
    assert 'Network is unreachable' in network['stderr']


@pytest.mark.asyncio
async def test_real_cancel_removes_container():
    before = containers()
    task = asyncio.create_task(execute_code_docker('while True: pass',timeout=30))
    try:
        for _ in range(100):
            if containers()-before:
                break
            if task.done():
                pytest.fail('Sandbox exited before cancellation check')
            await asyncio.sleep(.05)
        else:
            pytest.fail('Execution container never started')
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not containers()-before
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
