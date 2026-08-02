import re
import discord
from typing import List

def split_message_chunks(text: str, max_length: int = 1900) -> List[str]:
    """
    Splits long text into clean chunks for Discord messages (< 1900 chars).
    Intelligently splits at line breaks and code block boundaries to prevent
    broken Markdown formatting.
    """
    if not text:
        return ["*No output generated.*"]

    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    lines = text.split("\n")
    in_code_block = False
    code_block_lang = ""

    for line in lines:
        # Track code block state
        if line.startswith("```"):
            if in_code_block:
                in_code_block = False
                code_block_lang = ""
            else:
                in_code_block = True
                code_block_lang = line[3:].strip()

        # Check if adding this line exceeds max_length
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                # If inside a code block, close it at the end of this chunk
                if in_code_block:
                    current_chunk += "\n```"
                chunks.append(current_chunk)

                # Start new chunk and re-open code block if needed
                if in_code_block:
                    current_chunk = f"```{code_block_lang}\n" + line
                else:
                    current_chunk = line
            else:
                # Fallback for a single line longer than max_length
                sub_chunks = [line[i:i+max_length] for i in range(0, len(line), max_length)]
                chunks.extend(sub_chunks[:-1])
                current_chunk = sub_chunks[-1]
        else:
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line

    if current_chunk:
        chunks.append(current_chunk)

    return chunks

def compress_assistant_history(text: str, max_chars: int = 350) -> str:
    """
    Intelligent Assistant History Compressor.
    Replaces raw code blocks with semantic tags [Provided <lang> snippet (~N lines)]
    and extracts key summary lines up to ~350 chars (~75 tokens) for history efficiency.
    """
    if not text:
        return ""

    def replace_code_block(match: re.Match) -> str:
        lang = match.group(1).strip() if match.group(1) else "code"
        code_body = match.group(2) or ""
        line_count = len(code_body.strip().split("\n"))
        return f"\n[Provided {lang} snippet (~{line_count} lines)]\n"

    # Match fenced code blocks ```lang\ncode\n```
    pattern = r"```([a-zA-Z0-9_\-\+]*)\n(.*?)```"
    compressed = re.sub(pattern, replace_code_block, text, flags=re.DOTALL)

    # Clean up multiple newlines
    compressed = re.sub(r"\n{3,}", "\n\n", compressed).strip()

    # Truncate remaining text to max_chars if longer, preserving word boundary
    if len(compressed) > max_chars:
        trimmed = compressed[:max_chars]
        last_space = trimmed.rfind(" ")
        if last_space > 100:
            trimmed = trimmed[:last_space]
        compressed = trimmed + "..."

    return compressed
