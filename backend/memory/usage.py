"""Request-scoped accounting for successful physical model responses."""
from contextvars import ContextVar

usage_records: ContextVar[list | None] = ContextVar('zauq_usage_records', default=None)


def record_usage(provider: str, model: str, data: dict) -> None:
    records = usage_records.get()
    if records is None:
        return
    usage = data.get('usageMetadata') or data.get('usage') or {}
    input_tokens = usage.get('promptTokenCount', usage.get('prompt_tokens', usage.get('input_tokens')))
    output_tokens = usage.get('candidatesTokenCount', usage.get('completion_tokens', usage.get('output_tokens')))
    input_tokens = input_tokens if isinstance(input_tokens,int) and not isinstance(input_tokens,bool) and input_tokens >= 0 else None
    output_tokens = output_tokens if isinstance(output_tokens,int) and not isinstance(output_tokens,bool) and output_tokens >= 0 else None
    cache_read = usage.get('cache_read_input_tokens',0)
    cache_creation = usage.get('cache_creation_input_tokens',0)
    if input_tokens is not None:
        input_tokens += sum(value for value in (cache_read,cache_creation) if isinstance(value,int) and value >= 0)
    # Gemini thinking tokens are billable output even though they are hidden.
    if output_tokens is not None and usage.get('thoughtsTokenCount'):
        output_tokens += usage['thoughtsTokenCount']
    records.append({'provider':provider,'model':model,'input_tokens':input_tokens,'output_tokens':output_tokens,'cache_read_input_tokens':cache_read,'cache_creation_input_tokens':cache_creation})
