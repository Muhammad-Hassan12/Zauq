from backend.agent.rollout import feature_enabled
from backend.config import settings


def test_master_allowlists_and_profile_precedence(monkeypatch):
    monkeypatch.setattr(settings,'AGENT_RUNTIME_ENABLED',True)
    monkeypatch.setattr(settings,'AGENT_ALLOWED_GUILD_IDS','guild')
    assert not feature_enabled('agent','c','other')
    assert feature_enabled('agent','c','guild')
    assert not feature_enabled('agent','c','guild',{'agent_runtime_enabled':False},{'agent_runtime_enabled':True})
    assert feature_enabled('agent','c','guild',{'agent_runtime_enabled':True},{'agent_runtime_enabled':False})
    monkeypatch.setattr(settings,'AGENT_RUNTIME_ENABLED',False)
    assert not feature_enabled('agent','c','guild',{'agent_runtime_enabled':True})
