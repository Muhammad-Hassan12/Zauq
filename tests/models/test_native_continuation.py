from backend.models.gemini_client import GeminiClient
from backend.models.anthropic_client import AnthropicClient
from backend.models.deepseek_client import DeepSeekClient


def test_gemini_preserves_signature_parts_and_function_response_id():
    native = {'role':'model','parts':[{'thought':True,'text':'private','thoughtSignature':'sig'}, {'functionCall':{'id':'native-id','name':'web__search','args':{'query':'x'}},'thoughtSignature':'call-sig'}]}
    messages = [{'role':'user','content':'x'}, {'role':'assistant','_provider_continuation':{'provider':'gemini','content':native}}, {'role':'tool','name':'web.search','content':'ok','provider_call_id':'native-id'}]
    payload = GeminiClient(api_key='test')._prepare_payload(messages)
    assert payload['contents'][1] == native
    assert payload['contents'][2]['parts'][0]['functionResponse']['id'] == 'native-id'


def test_anthropic_preserves_signed_and_redacted_blocks():
    blocks = [{'type':'thinking','thinking':'private','signature':'sig'}, {'type':'redacted_thinking','data':'opaque'}, {'type':'tool_use','id':'c','name':'web__search','input':{'query':'x'}}]
    _, messages = AnthropicClient(api_key='test')._format_messages_and_system([{'role':'assistant','_provider_continuation':{'provider':'anthropic','content':blocks}}])
    assert messages[0]['content'] == blocks


def test_deepseek_preserves_reasoning_only_inside_native_continuation():
    native = {'role':'assistant','content':None,'reasoning_content':'private','tool_calls':[{'id':'c','type':'function','function':{'name':'web__search','arguments':'{}'}}]}
    _, payload = DeepSeekClient(api_key='test')._build_payload([{'role':'assistant','_provider_continuation':{'provider':'deepseek','content':native}}], model_name='deepseek-flash')
    assert payload['messages'][0] == native


def test_gemini_parallel_results_share_one_user_turn():
    messages = [{'role':'user','content':'x'}, {'role':'assistant','content':'checking'},
                {'role':'tool','name':'web.search','provider_call_id':'a','content':'one'},
                {'role':'tool','name':'web.fetch','provider_call_id':'b','content':'two'}]
    payload = GeminiClient(api_key='test')._prepare_payload(messages)
    assert len(payload['contents']) == 3
    assert [p['functionResponse']['id'] for p in payload['contents'][-1]['parts']] == ['a','b']
