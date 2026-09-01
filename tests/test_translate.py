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


# --- Vision: image_url content parts ---


def test_openai_image_to_anthropic_base64() -> None:
    body = {
        "model": "m",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "what is this?"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                ],
            }
        ],
    }
    out = openai_to_anthropic(body)
    content = out["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image"
    assert content[1]["source"]["type"] == "base64"
    assert content[1]["source"]["media_type"] == "image/png"
    assert content[1]["source"]["data"] == "AAAA"


def test_openai_image_to_anthropic_url() -> None:
    body = {"model": "m", "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://x/y.png"}}]}]}
    out = openai_to_anthropic(body)
    src = out["messages"][0]["content"][0]["source"]
    assert src["type"] == "url"
    assert src["url"] == "https://x/y.png"


def test_openai_image_to_gemini_base64() -> None:
    body = {
        "model": "m",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,BBBB"}}
                ],
            }
        ],
    }
    out = openai_to_gemini(body)
    part = out["contents"][0]["parts"][0]
    assert part["inline_data"]["mime_type"] == "image/jpeg"
    assert part["inline_data"]["data"] == "BBBB"


def test_openai_image_to_gemini_url() -> None:
    body = {
        "model": "m",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "https://x/p.png"}}
                ],
            }
        ],
    }
    out = openai_to_gemini(body)
    assert out["contents"][0]["parts"][0]["file_data"]["file_uri"] == "https://x/p.png"


def test_anthropic_image_to_openai() -> None:
    body = {
        "model": "m",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "desc"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/webp", "data": "CCCC"}},
                ],
            }
        ],
    }
    out = anthropic_to_openai(body)
    content = out["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/webp;base64,CCCC")


def test_gemini_inline_data_to_openai() -> None:
    body = {
        "model": "m",
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": "x"},
                    {"inline_data": {"mime_type": "image/png", "data": "DDDD"}},
                ],
            }
        ],
    }
    out = gemini_to_openai(body)
    msg = [m for m in out["messages"] if isinstance(m.get("content"), list)][0]
    image_part = [p for p in msg["content"] if p["type"] == "image_url"][0]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,DDDD")


# --- Tools: request tool_calls -> gemini functionCall; response tool_calls ---


def test_openai_tool_calls_to_gemini_function_call() -> None:
    body = {
        "model": "m",
        "messages": [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "weather", "arguments": "{\"city\": \"x\"}"}}
            ]},
            {"role": "tool", "tool_call_id": "c1", "content": "20C"},
        ],
    }
    out = openai_to_gemini(body)
    model_msg = out["contents"][0]
    assert model_msg["role"] == "model"
    assert model_msg["parts"][0]["functionCall"]["name"] == "weather"
    tool_msg = out["contents"][1]
    assert tool_msg["parts"][0]["functionResponse"]["name"] == "c1"


def test_translate_response_anthropic_tool_use() -> None:
    body = {
        "content": [
            {"type": "text", "text": "calling"},
            {"type": "tool_use", "id": "toolu_1", "name": "weather", "input": {"city": "x"}},
        ],
        "stop_reason": "tool_use",
    }
    out = translate_response("anthropic", "openai", body)
    msg = out["choices"][0]["message"]
    assert msg["content"] == "calling"
    assert msg["tool_calls"][0]["id"] == "toolu_1"
    assert msg["tool_calls"][0]["function"]["name"] == "weather"
    assert out["choices"][0]["finish_reason"] == "tool_use"


def test_translate_response_gemini_function_call() -> None:
    body = {"candidates": [{"content": {"parts": [{"functionCall": {"name": "weather", "args": {"city": "x"}}}]}}]}
    out = translate_response("gemini", "openai", body)
    msg = out["choices"][0]["message"]
    assert msg["tool_calls"][0]["function"]["name"] == "weather"
    assert msg["tool_calls"][0]["function"]["arguments"] == '{"city": "x"}'
