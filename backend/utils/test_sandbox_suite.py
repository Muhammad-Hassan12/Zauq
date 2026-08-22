import asyncio
from backend.sandbox.code_runner import execute_code
from bot.commands.exec_slash import extract_code_and_lang

async def run_sandbox_tests():
    print("🚀 Starting Zauq Multi-Input Sandbox & Code Execution Test Suite...\n")

    # 1. Test Code Fence Extraction Helper
    print("1. Testing Code Fence Extraction Helper...")
    sample_discord_msg = "Here is the solution to your problem:\n```python\ndef fib(n):\n    return n if n <= 1 else fib(n-1) + fib(n-2)\n\nprint([fib(i) for i in range(7)])\n```\nHope this helps!"
    code, lang = extract_code_and_lang(sample_discord_msg)
    assert lang == "python", f"Incorrect lang: {lang}"
    assert "def fib" in code, "Failed to extract function body"
    assert "print([fib" in code, "Failed to extract print call"
    print(f"   Extracted Language: {lang}")
    print(f"   Extracted Code:\n{code}")
    print("   ✅ Code fence parser working cleanly.\n")

    # 2. Test JavaScript Fence Extraction
    print("2. Testing JavaScript Fence Extraction...")
    js_msg = "```javascript\nconst arr = [1, 2, 3, 4];\nconsole.log(arr.map(x => x * 10));\n```"
    js_code, js_lang = extract_code_and_lang(js_msg)
    assert js_lang == "javascript", f"Incorrect lang: {js_lang}"
    assert "map" in js_code, "Failed to extract JS code"
    print("   ✅ JavaScript fence extraction verified.\n")

    # 3. Test Multiline Python Execution in Docker Sandbox
    print("3. Testing Multiline Python Execution in Docker Sandbox...")
    py_multiline = """
def is_prime(n):
    if n < 2: return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0: return False
    return True

primes = [x for x in range(30) if is_prime(x)]
print(f"Primes under 30: {primes}")
"""
    res_py = await execute_code(py_multiline, language="python", timeout=5.0)
    assert res_py.get("success") is True, f"Python execution failed: {res_py}"
    assert "Primes under 30: [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]" in res_py.get("stdout", ""), f"Unexpected stdout: {res_py.get('stdout')}"
    print(f"   Python Output: {res_py.get('stdout').strip()}")
    print(f"   Execution Latency: {res_py.get('execution_time_ms')} ms")
    print("   ✅ Multiline Python execution verified.\n")

    # 4. Test Node.js (JavaScript) Execution
    print("4. Testing JavaScript (Node.js) Execution in Docker Sandbox...")
    js_multiline = """
const items = [{id: 1, name: 'Zauq'}, {id: 2, name: 'AgenticEra'}];
const result = items.map(i => i.name.toUpperCase()).join(' - ');
console.log(`PROCESSED: ${result}`);
"""
    res_js = await execute_code(js_multiline, language="javascript", timeout=5.0)
    assert res_js.get("success") is True, f"JS execution failed: {res_js}"
    assert "PROCESSED: ZAUQ - AGENTICERA" in res_js.get("stdout", ""), f"Unexpected stdout: {res_js.get('stdout')}"
    print(f"   Node.js Output: {res_js.get('stdout').strip()}")
    print("   ✅ Multiline JavaScript execution verified.\n")

    # 5. Test Bash Script Execution
    print("5. Testing Bash Execution in Docker Sandbox...")
    bash_script = """
echo "Step 1: Init"
printf "Sum: %d\\n" "$((10 + 25))"
echo "Step 2: Done"
"""
    res_bash = await execute_code(bash_script, language="bash", timeout=5.0)
    assert res_bash.get("success") is True, f"Bash execution failed: {res_bash}"
    assert "Sum: 35" in res_bash.get("stdout", ""), f"Unexpected stdout: {res_bash.get('stdout')}"
    print(f"   Bash Output: {res_bash.get('stdout').strip()}")
    print("   ✅ Bash pipeline execution verified.\n")

    print("🎉 ALL MULTI-INPUT SANDBOX TESTS PASSED! (100% PASS RATE)")

if __name__ == "__main__":
    asyncio.run(run_sandbox_tests())
