"""Allow research citations only to retrieved source URLs."""
import re


def validate_citations(answer: str, source_urls: set[str]) -> str:
    def replace(match):
        title, url = match.groups()
        return match.group(0) if url in source_urls else f'{title} (unverified source omitted)'
    # Keep code examples intact; their URLs are examples, not research citations.
    parts = re.split(r'(```[\s\S]*?```)', answer)
    return ''.join(part if part.startswith('```') else re.sub(r'\[([^\]\n]+)\]\((https?://[^\s)]+)\)', replace, part) for part in parts)
