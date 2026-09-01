"""Wire-protocol translation between OpenAI, Anthropic and Gemini.

Pure functions — never raise in hot paths, best-effort mapping.
Protocol aliases "google"/"vertex" normalize to "gemini".
No hardcoded model names: the target model is passed through.
"""

from __future__ import annotations

import copy
import json
from typing import Any

DEFAULT_MAX_TOKENS = 4096


def normalize_protocol(protocol: str) -> str:
    p = protocol.strip().lower()
    if p in ("google", "vertex"):
        return "gemini"
    return p


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            elif block is not None:
                parts.append(str(block))
        return "\n".join(p for p in parts if p)
    return "" if content is None else str(content)


def _openai_content_blocks(content: Any) -> list[dict[str, Any]]:
    """Normalize OpenAI message content into blocks:
    {kind:"text",text} | {kind:"image_url",url,detail}."""
    if isinstance(content, str):
        return [{"kind": "text", "text": content}] if content else []
    if isinstance(content, list):
        out: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                out.append({"kind": "text", "text": block["text"]})
            elif block.get("type") == "image_url":
                iu = block.get("image_url") or {}
                url = iu.get("url", "") if isinstance(iu, dict) else ""
                if url:
                    out.append({"kind": "image_url", "url": url, "detail": iu.get("detail")})
        return out
    return []


def _image_url_to_anthropic(url: str) -> dict[str, Any]:
    """OpenAI image_url -> Anthropic image block (base64 or url source)."""
    if url.startswith("data:"):
        header, _, b64 = url.partition(",")
        media = header.split(";")[0].replace("data:", "") or "image/png"
        return {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}}
    return {"type": "image", "source": {"type": "url", "url": url}}


def _image_url_to_gemini(url: str) -> dict[str, Any]:
    """OpenAI image_url -> Gemini part (inline_data or file_data)."""
    if url.startswith("data:"):
        header, _, b64 = url.partition(",")
        mime = header.split(";")[0].replace("data:", "") or "image/png"
        return {"inline_data": {"mime_type": mime, "data": b64}}
    return {"file_data": {"file_uri": url}}


def _anthropic_image_to_openai(block: dict[str, Any]) -> list[dict[str, Any]]:
    """Anthropic image block -> OpenAI image_url content parts."""
    src = block.get("source") or {}
    if src.get("type") == "base64":
        media = src.get("media_type", "image/png")
        return [{"type": "image_url", "image_url": {"url": f"data:{media};base64,{src.get('data','')}"}}]
    if src.get("type") == "url":
        return [{"type": "image_url", "image_url": {"url": src.get("url", "")}}]
    return []


def _gemini_part_to_openai(part: dict[str, Any]) -> list[dict[str, Any]]:
    if "text" in part:
        return [{"type": "text", "text": part["text"]}]
    if "inline_data" in part:
        idata = part["inline_data"]
        mime = idata.get("mime_type", "image/png") if isinstance(idata, dict) else "image/png"
        data = idata.get("data", "") if isinstance(idata, dict) else ""
        return [{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}]
    if "file_data" in part:
        fdata = part["file_data"]
        uri = fdata.get("file_uri", "") if isinstance(fdata, dict) else ""
        return [{"type": "image_url", "image_url": {"url": uri}}]
    if "functionCall" in part:
        fc = part["functionCall"]
        return [
            {
                "type": "function",
                "id": fc.get("name", ""),
                "name": fc.get("name", ""),
                "arguments": json.dumps(fc.get("args", {})),
            }
        ]
    if "functionResponse" in part:
        fr = part["functionResponse"]
        return [
            {
                "type": "tool_result",
                "tool_use_id": fr.get("name", ""),
                "content": json.dumps(fr.get("response", {})),
            }
        ]
    return []


def _openai_to_anthropic_system(messages: list[dict[str, Any]]) -> str:
    system_parts = [m.get("content") for m in messages if m.get("role") == "system"]
    return "\n".join(_text_of(c) for c in system_parts if c is not None)


def _openai_to_anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            continue
        if role == "tool":
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id", ""),
                            "content": _text_of(msg.get("content")),
                        }
                    ],
                }
            )
            continue
        if role == "assistant" and msg.get("tool_calls"):
            blocks: list[dict[str, Any]] = []
            text = _text_of(msg.get("content"))
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": json.loads(fn.get("arguments", "{}") or "{}"),
                    }
                )
            out.append({"role": "assistant", "content": blocks})
            continue
        # User/assistant content with optional images
        content = msg.get("content")
        cblocks = _openai_content_blocks(content)
        if any(b["kind"] == "image_url" for b in cblocks):
            # If there are images, build full content array
            anthro_content: list[dict[str, Any]] = []
            for b in cblocks:
                if b["kind"] == "text":
                    anthro_content.append({"type": "text", "text": b["text"]})
                elif b["kind"] == "image_url" and b["url"]:
                    anthro_content.append(_image_url_to_anthropic(b["url"]))
            out.append({"role": role if role in ("user", "assistant") else "user", "content": anthro_content})
        else:
            out.append({"role": role if role in ("user", "assistant") else "user", "content": _text_of(content)})
    return out


def openai_to_anthropic(body: dict[str, Any]) -> dict[str, Any]:
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    system = _openai_to_anthropic_system(messages)
    out: dict[str, Any] = {
        "model": body.get("model", ""),
        "messages": _openai_to_anthropic_messages(messages),
        "max_tokens": body.get("max_tokens") or DEFAULT_MAX_TOKENS,
    }
    if system:
        out["system"] = system
    if body.get("temperature") is not None:
        out["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        out["top_p"] = body["top_p"]
    stop = body.get("stop")
    if isinstance(stop, str):
        out["stop_sequences"] = [stop]
    elif isinstance(stop, list):
        out["stop_sequences"] = stop
    tools = body.get("tools")
    if tools:
        out["tools"] = [
            {
                "name": t["function"].get("name", ""),
                "description": t["function"].get("description", ""),
                "input_schema": t["function"].get("parameters", {"type": "object"}),
            }
            for t in tools
            if isinstance(t, dict) and isinstance(t.get("function"), dict)
        ]
    if body.get("tool_choice") is not None:
        out["tool_choice"] = body["tool_choice"]
    if body.get("stream") is not None:
        out["stream"] = body["stream"]
    return out


def _anthropic_to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, list):
            text_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
            image_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "image"]
            tool_use_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
            tool_result_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
            if role == "assistant" and tool_use_blocks:
                out.append(
                    {
                        "role": "assistant",
                        "content": _text_of(text_blocks) or None,
                        "tool_calls": [
                            {
                                "id": b.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": b.get("name", ""),
                                    "arguments": json.dumps(b.get("input", {})),
                                },
                            }
                            for b in tool_use_blocks
                        ],
                    }
                )
                continue
            if role == "user" and tool_result_blocks:
                for b in tool_result_blocks:
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": b.get("tool_use_id", ""),
                            "content": _text_of(b.get("content")),
                        }
                    )
                continue
            if role in ("user", "assistant") and image_blocks:
                parts: list[dict[str, Any]] = []
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                        parts.append({"type": "text", "text": b["text"]})
                    elif isinstance(b, dict) and b.get("type") == "image":
                        parts.extend(_anthropic_image_to_openai(b))
                out.append({"role": role, "content": parts})
                continue
        out.append({"role": role if role in ("user", "assistant") else "user", "content": _text_of(content)})
    return out


def anthropic_to_openai(body: dict[str, Any]) -> dict[str, Any]:
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    out: dict[str, Any] = {
        "model": body.get("model", ""),
        "messages": [],
    }
    system = body.get("system")
    if system:
        out["messages"].append({"role": "system", "content": _text_of(system)})
    out["messages"].extend(_anthropic_to_openai_messages(messages))
    if body.get("max_tokens") is not None:
        out["max_tokens"] = body["max_tokens"]
    if body.get("temperature") is not None:
        out["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        out["top_p"] = body["top_p"]
    stop_seq = body.get("stop_sequences")
    if stop_seq:
        out["stop"] = stop_seq if len(stop_seq) > 1 else stop_seq[0]
    tools = body.get("tools")
    if tools:
        out["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object"}),
                },
            }
            for t in tools
            if isinstance(t, dict)
        ]
    if body.get("tool_choice") is not None:
        out["tool_choice"] = body["tool_choice"]
    if body.get("stream") is not None:
        out["stream"] = body["stream"]
    return out


def _openai_to_gemini_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            continue
        if role == "tool":
            # functionResponse part (no per-call id in gemini; use tool_call_id as name)
            tid = msg.get("tool_call_id", "")
            out.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": tid or "function_result",
                                "response": {"result": _text_of(msg.get("content"))},
                            }
                        }
                    ],
                }
            )
            continue
        if role == "assistant" and msg.get("tool_calls"):
            parts: list[dict[str, Any]] = []
            text = _text_of(msg.get("content"))
            if text:
                parts.append({"text": text})
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                parts.append(
                    {
                        "functionCall": {
                            "name": fn.get("name", ""),
                            "args": json.loads(fn.get("arguments", "{}") or "{}"),
                        }
                    }
                )
            out.append({"role": "model", "parts": parts})
            continue
        content_parts: list[dict[str, Any]] = []
        for b in _openai_content_blocks(msg.get("content")):
            if b["kind"] == "text":
                content_parts.append({"text": b["text"]})
            elif b["kind"] == "image_url" and b["url"]:
                content_parts.append(_image_url_to_gemini(b["url"]))
        out.append({"role": "user" if role == "user" else "model", "parts": content_parts})
    return out
def openai_to_gemini(body: dict[str, Any]) -> dict[str, Any]:
    body = copy.deepcopy(body)
    messages = body.get("messages") or []
    out: dict[str, Any] = {
        "model": body.get("model", ""),
        "contents": _openai_to_gemini_contents(messages),
    }
    system_parts = [m.get("content") for m in messages if m.get("role") == "system"]
    system_text = "\n".join(_text_of(c) for c in system_parts if c is not None)
    if system_text:
        out["systemInstruction"] = {"parts": [{"text": system_text}]}
    gen_cfg: dict[str, Any] = {}
    if body.get("temperature") is not None:
        gen_cfg["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        gen_cfg["topP"] = body["top_p"]
    if body.get("max_tokens") is not None:
        gen_cfg["maxOutputTokens"] = body["max_tokens"]
    if gen_cfg:
        out["generationConfig"] = gen_cfg
    tools = body.get("tools")
    if tools:
        out["tools"] = [
            {
                "functionDeclarations": [
                    {
                        "name": t["function"].get("name", ""),
                        "description": t["function"].get("description", ""),
                        "parameters": t["function"].get("parameters", {"type": "object"}),
                    }
                    for t in tools
                    if isinstance(t, dict) and isinstance(t.get("function"), dict)
                ]
            }
        ]
    if body.get("stream") is not None:
        out["stream"] = body["stream"]
    return out


def gemini_to_openai(body: dict[str, Any]) -> dict[str, Any]:
    body = copy.deepcopy(body)
    out: dict[str, Any] = {
        "model": body.get("model", ""),
        "messages": [],
    }
    si = body.get("systemInstruction")
    if si:
        out["messages"].append({"role": "system", "content": _text_of(si)})
    for c in body.get("contents") or []:
        role = "user" if c.get("role") == "user" else "assistant"
        parts_list = c.get("parts") or []
        # Accumulate text + image_url into a single content array per message
        text_parts: list[str] = []
        image_parts: list[dict[str, Any]] = []
        for part in parts_list:
            if not isinstance(part, dict):
                continue
            converted = _gemini_part_to_openai(part)
            for item in converted:
                if item["type"] == "text":
                    text_parts.append(item["text"])
                elif item["type"] == "image_url":
                    image_parts.append(item)
                elif item["type"] == "function":
                    out["messages"].append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": item["id"],
                                    "type": "function",
                                    "function": {"name": item["name"], "arguments": item["arguments"]},
                                }
                            ],
                        }
                    )
                elif item["type"] == "tool_result":
                    out["messages"].append(
                        {"role": "tool", "tool_call_id": item["tool_use_id"], "content": item["content"]}
                    )
        if text_parts or image_parts:
            content = "\n".join(text_parts) if text_parts else ""
            if image_parts:
                # Build content array with text + image_url
                content_list: list[dict[str, Any]] = []
                if text_parts:
                    content_list.append({"type": "text", "text": "\n".join(text_parts)})
                for img in image_parts:
                    content_list.append(img)
                out["messages"].append({"role": role, "content": content_list})
            else:
                out["messages"].append({"role": role, "content": content})
    gc = body.get("generationConfig") or {}
    if gc.get("temperature") is not None:
        out["temperature"] = gc["temperature"]
    if gc.get("topP") is not None:
        out["top_p"] = gc["topP"]
    if gc.get("maxOutputTokens") is not None:
        out["max_tokens"] = gc["maxOutputTokens"]
    tools = body.get("tools")
    if tools:
        out["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": fd.get("name", ""),
                    "description": fd.get("description", ""),
                    "parameters": fd.get("parameters", {"type": "object"}),
                },
            }
            for t in tools
            if isinstance(t, dict)
            for fd in t.get("functionDeclarations", [])
            if isinstance(fd, dict)
        ]
    if body.get("stream") is not None:
        out["stream"] = body["stream"]
    return out


def translate_request(protocol_from: str, protocol_to: str, body: dict[str, Any], model: str) -> dict[str, Any]:
    src = normalize_protocol(protocol_from)
    dst = normalize_protocol(protocol_to)
    if src == dst:
        out = copy.deepcopy(body)
        out["model"] = model
        return out
    if src == "openai" and dst == "anthropic":
        out = openai_to_anthropic(body)
    elif src == "openai" and dst == "gemini":
        out = openai_to_gemini(body)
    elif src == "anthropic" and dst == "openai":
        out = anthropic_to_openai(body)
    elif src == "gemini" and dst == "openai":
        out = gemini_to_openai(body)
    else:
        out = copy.deepcopy(body)
    out["model"] = model
    return out


def translate_response(protocol_from: str, protocol_to: str, body: dict[str, Any]) -> dict[str, Any]:
    src = normalize_protocol(protocol_from)
    dst = normalize_protocol(protocol_to)
    if src == dst:
        return copy.deepcopy(body)
    out = copy.deepcopy(body)
    if src == "anthropic" and dst == "openai":
        text = ""
        content = out.get("content")
        tool_calls: list[dict[str, Any]] = []
        if isinstance(content, list):
            text = "\n".join(
                _text_of(b.get("text")) for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
            tool_calls = [
                {
                    "id": b.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": b.get("name", ""),
                        "arguments": json.dumps(b.get("input", {})),
                    },
                }
                for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use"
            ]
        else:
            text = _text_of(content)
        message: dict[str, Any] = {"role": "assistant", "content": text}
        if tool_calls:
            message["tool_calls"] = tool_calls
        out["choices"] = [
            {
                "index": 0,
                "message": message,
                "finish_reason": out.get("stop_reason", "stop"),
            }
        ]
        out["usage"] = {
            "prompt_tokens": (out.get("usage") or {}).get("input_tokens", 0),
            "completion_tokens": (out.get("usage") or {}).get("output_tokens", 0),
            "total_tokens": (
                (out.get("usage") or {}).get("input_tokens", 0)
                + (out.get("usage") or {}).get("output_tokens", 0)
            ),
        }
        out.pop("content", None)
    elif src == "gemini" and dst == "openai":
        text = ""
        tool_calls = []
        candidates = out.get("candidates") or []
        if candidates:
            parts = candidates[0].get("content", {}).get("parts") or []
            for p in parts:
                if not isinstance(p, dict):
                    continue
                if "text" in p:
                    text += p.get("text", "")
                elif "functionCall" in p:
                    fc = p["functionCall"]
                    tool_calls.append(
                        {
                            "id": fc.get("name", ""),
                            "type": "function",
                            "function": {
                                "name": fc.get("name", ""),
                                "arguments": json.dumps(fc.get("args", {})),
                            },
                        }
                    )
        message = {"role": "assistant", "content": text}
        if tool_calls:
            message["tool_calls"] = tool_calls
        out["choices"] = [{"index": 0, "message": message, "finish_reason": "stop"}]
        usage = out.get("usageMetadata") or {}
        out["usage"] = {
            "prompt_tokens": usage.get("promptTokenCount", 0),
            "completion_tokens": usage.get("candidatesTokenCount", 0),
            "total_tokens": usage.get("totalTokenCount", 0),
        }
    return out


__all__ = [
    "normalize_protocol",
    "openai_to_anthropic",
    "anthropic_to_openai",
    "openai_to_gemini",
    "gemini_to_openai",
    "translate_request",
    "translate_response",
]
