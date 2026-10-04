from backend.models.qwen_client import QwenClient
from backend.models.anthropic_client import AnthropicClient
from backend.models.gemini_client import GeminiClient
from backend.models.openai_compatible_client import OpenAICompatibleClient
from backend.models.capabilities import supports_thinking

MEDIA = [{'type':'image','mime_type':'image/png','bytes_b64':'aW1hZ2U='}]
MESSAGES = [{'role':'user','content':'read image'}, {'role':'assistant','content':'checking'}, {'role':'tool','tool_call_id':'c','name':'web.search','content':'result'}]


def test_qwen_media_kept_on_original_user_turn():
    _, payload = QwenClient(api_key='test')._build_payload(MESSAGES, model_name='qwen-vl-plus', media_parts=MEDIA)
    assert payload['messages'][0]['content'][1]['image_url']['url'].endswith('aW1hZ2U=')
    assert payload['messages'][-1]['content'] == 'result'


def test_native_media_survives_tool_continuation():
    payload = GeminiClient(api_key='test')._prepare_payload(MESSAGES, media_parts=MEDIA)
    assert payload['contents'][0]['parts'][1]['inlineData']['data'] == 'aW1hZ2U='
    _, messages = AnthropicClient(api_key='test')._format_messages_and_system(MESSAGES, media_parts=MEDIA, model_name='claude-sonnet-4-5')
    assert messages[0]['content'][0]['type'] == 'image'
    assert messages[-1]['content'][0]['type'] == 'tool_result'


def test_thinking_does_not_inject_private_reasoning_directives():
    client = OpenAICompatibleClient('http://local')
    assert client._format_messages([], 'normal prompt', True) == [{'role':'system','content':'normal prompt'}]
    assert not supports_thinking('gemini','gemma-4-31b-it')
    payload = GeminiClient(api_key='test')._prepare_payload([{'role':'user','content':'x'}], thinking_enabled=True, model_name='gemma-4-31b-it')
    assert 'thinkingConfig' not in payload['generationConfig']


def test_qwen_hybrid_thinking_has_explicit_off():
    _, payload = QwenClient(api_key='test')._build_payload([], model_name='qwen3.8-flash', thinking_enabled=False)
    assert payload['enable_thinking'] is False
