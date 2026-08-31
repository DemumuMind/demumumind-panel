"""Protocol translation tests — OpenAI <-> Anthropic <-> Gemini."""

from __future__ import annotations

from app.services.translate import (
    anthropic_to_openai,
    gemini_to_openai,
    openai_to_anthropic,
    openai_to_gemini,
    translate_request,
    translate_response,
)


def test_normalize_protocol_aliases() -> None:
    from app.services.translate import normalize_protocol

    assert normalize_protocol("google") == "gemini"
    assert normalize_protocol("vertex") == "gemini"
    assert normalize_protocol("OpenAI") == "openai"


def test_openai_to_anthropic_system_and_tools() -> None:
    body = {
        "model": "my-model",
        "messages": [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {"name": "get_weather", "description": "weather", "parameters": {"type": "object"}},
            }
        ],
        "temperature": 0.5,
    }
    out = openai_to_anthropic(body)
    assert out["system"] == "You are helpful"
    assert out["messages"][0]["role"] == "user"
    assert out["tools"][0]["name"] == "get_weather"
    assert out["tools"][0]["input_schema"] == {"type": "object"}
    assert out["temperature"] == 0.5
    assert out["max_tokens"] > 0


def test_openai_to_anthropic_tool_messages() -> None:
    body = {
        "model": "m",
        "messages": [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": "result"},
        ],
    }
    out = openai_to_anthropic(body)
    assert out["messages"][0]["content"][0]["type"] == "tool_use"
    assert out["messages"][1]["content"][0]["type"] == "tool_result"
    assert out["messages"][1]["content"][0]["tool_use_id"] == "call_1"


def test_anthropic_to_openai() -> None:
    body = {
        "model": "m",
        "system": "Be brief",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 128,
    }
    out = anthropic_to_openai(body)
    assert out["messages"][0]["role"] == "system"
    assert out["messages"][1]["role"] == "user"
    assert out["max_tokens"] == 128


def test_openai_to_gemini() -> None:
    body = {
        "model": "m",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ],
        "max_tokens": 256,
        "top_p": 0.9,
    }
    out = openai_to_gemini(body)
    assert out["systemInstruction"]["parts"][0]["text"] == "sys"
    assert out["contents"][0]["role"] == "user"
    assert out["generationConfig"]["maxOutputTokens"] == 256
    assert out["generationConfig"]["topP"] == 0.9


def test_gemini_to_openai() -> None:
    body = {
        "model": "m",
        "contents": [{"role": "user", "parts": [{"text": "hi"}]}],
        "generationConfig": {"maxOutputTokens": 64},
    }
    out = gemini_to_openai(body)
    assert out["messages"][0]["content"] == "hi"
    assert out["max_tokens"] == 64


def test_translate_request_roundtrip_openai_to_anthropic() -> None:
    body = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    out = translate_request("openai", "anthropic", body, "claude-internal")
    assert out["model"] == "claude-internal"
    assert "messages" in out


def test_translate_response_anthropic_to_openai() -> None:
    body = {"content": [{"type": "text", "text": "answer"}], "usage": {"input_tokens": 5, "output_tokens": 3}}
    out = translate_response("anthropic", "openai", body)
    assert out["choices"][0]["message"]["content"] == "answer"
    assert out["usage"]["prompt_tokens"] == 5
    assert out["usage"]["completion_tokens"] == 3
