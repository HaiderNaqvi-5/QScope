import json

import httpx
import pytest

from app.services.llm.context import build_context, path_allowed, redact
from app.services.llm.providers.groq import GroqProvider
from app.services.llm.schemas import LLMJob, LLMRequest


def test_context_is_bounded_redacted_and_manifested(tmp_path):
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("\n".join(["safe = True", 'api_key = "gsk_abcdefghijklmnop"'] * 200))
    context, manifest = build_context(tmp_path, "src/app.py", 200, radius=200)
    assert "gsk_abcdefghijklmnop" not in context
    assert "REDACTED_SECRET" in context
    assert len(context.splitlines()) <= 252
    assert manifest[0].redaction_count > 0
    assert len(manifest[0].sha256) == 64


def test_forbidden_and_outside_paths_are_rejected(tmp_path):
    assert not path_allowed(tmp_path, tmp_path / ".env")
    assert not path_allowed(tmp_path, tmp_path / "node_modules" / "x.js")
    assert not path_allowed(tmp_path, tmp_path.parent / "outside.py")
    assert build_context(tmp_path, ".env", 1) == ("", [])


def test_redacts_common_credentials():
    safe, count = redact("password=hunter2 token: abcdefghijklmnop")
    assert "hunter2" not in safe and "abcdefghijklmnop" not in safe
    assert count == 2


@pytest.mark.asyncio
async def test_provider_sends_redacted_context_and_validates_advisory():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        result = {"summary": "Use parameterization", "remediation": ["Replace interpolation"],
                  "evidence_level": "CRITICAL"}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(result)}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GroqProvider(api_key="test-key", base_url="https://example.test/v1", timeout=1,
                            max_retries=0, client=client)
    request = LLMRequest(job=LLMJob.EXPLAIN, finding={"title": "SQL"}, context="[REDACTED_SECRET:credential]",
                         model="test-model", correlation_id="corr")
    response = await provider.generate_structured(request)
    sent = captured["messages"][1]["content"]
    assert "test-key" not in sent
    assert "REDACTED_SECRET" in sent
    assert response.result.evidence_level == "ADVISORY"
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_missing_key_is_deterministic():
    provider = GroqProvider(api_key="", base_url="https://example.test/v1", timeout=1, max_retries=0)
    request = LLMRequest(job=LLMJob.EXPLAIN, finding={}, model="test", correlation_id="corr")
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        await provider.generate_structured(request)
    await provider.close()
