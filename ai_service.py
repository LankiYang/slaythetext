from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


_DOTENV_LOADED = False


def _load_dotenv() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    for path in (Path.cwd() / ".env", Path(__file__).resolve().parent / ".env"):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value
        break


def _load_pi_provider() -> dict[str, Any]:
    provider_id = os.getenv("PI_PROVIDER")
    model_id = os.getenv("PI_MODEL")
    if not provider_id:
        return {}
    config_path = Path.home() / ".pi" / "agent" / "models.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        provider = config.get("providers", {}).get(provider_id, {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}
    if not isinstance(provider, dict):
        return {}
    result = {
        "base_url": provider.get("baseUrl"),
        "api_key": provider.get("apiKey"),
        "api": provider.get("api"),
        "headers": provider.get("headers", {}),
    }
    models = provider.get("models", [])
    if model_id and isinstance(models, list) and not any(
        isinstance(model, dict) and model.get("id") == model_id for model in models
    ):
        result["model"] = None
    else:
        result["model"] = model_id
    return result


def _runtime_config() -> dict[str, Any]:
    pi_config = _load_pi_provider()
    explicit_key = os.getenv("OPENAI_API_KEY", "").strip()
    explicit_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    explicit_model = os.getenv("SLAYTHETEXT_AI_MODEL", "").strip()
    return {
        "api_key": explicit_key or pi_config.get("api_key"),
        "base_url": explicit_base_url or pi_config.get("base_url") or "https://api.openai.com/v1",
        "model": explicit_model or pi_config.get("model") or "gpt-4o-mini",
        "api": pi_config.get("api") or "openai-chat",
        "headers": pi_config.get("headers") if isinstance(pi_config.get("headers"), dict) else {},
        "provider": os.getenv("PI_PROVIDER", "") or "explicit",
    }


def _extract_chat_content(payload: dict[str, Any]) -> str | None:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") for item in content if isinstance(item, dict)
        )
    return content if isinstance(content, str) else None


def _extract_response_content(payload: dict[str, Any]) -> str | None:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text
    output = payload.get("output", [])
    if not isinstance(output, list):
        return None
    parts = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for content_item in content:
            if isinstance(content_item, dict) and isinstance(content_item.get("text"), str):
                parts.append(content_item["text"])
    return "".join(parts) or None


def _endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _post_json(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout: float = 30,
) -> dict[str, Any] | None:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def online_available() -> bool:
    _load_dotenv()
    return bool(_runtime_config().get("api_key"))


def _stream_delta(payload: dict[str, Any], api: str) -> str:
    if api == "openai-responses":
        if payload.get("type") == "response.output_text.delta":
            delta = payload.get("delta")
            return delta if isinstance(delta, str) else ""
        return ""

    try:
        delta = payload["choices"][0].get("delta", {}).get("content", "")
    except (IndexError, KeyError, TypeError):
        return ""
    if isinstance(delta, list):
        return "".join(
            item.get("text", "") for item in delta if isinstance(item, dict)
        )
    return delta if isinstance(delta, str) else ""


def _post_stream_text(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    api: str,
    on_text: Callable[[str], None] | None = None,
    timeout: float = 30,
) -> str | None:
    request = urllib.request.Request(
        url,
        data=json.dumps({**body, "stream": True}, ensure_ascii=False).encode("utf-8"),
        headers={
            **headers,
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    parts: list[str] = []
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                delta = _stream_delta(payload, api)
                if not delta:
                    continue
                parts.append(delta)
                if on_text is not None:
                    on_text(delta)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None
    return "".join(parts) or None


def _clean_json_content(content: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())


def request_event(state: dict[str, Any], memory: list[dict[str, Any]]) -> dict[str, Any] | None:
    system_prompt = """
你是一个中文 roguelike 文字游戏的游戏主持人。请根据玩家状态创作一个简短、有风险和取舍的高塔事件。
只返回 JSON，不要 Markdown，不要额外解释。JSON 必须符合：
{
  "title": "不超过 20 个字的标题",
  "story": "不超过 180 个字的事件叙事",
  "choices": [
    {
      "id": "英文短 ID",
      "text": "中文选项，不超过 40 个字",
      "result": "中文结果，不超过 100 个字",
      "effects": [
        {"type": "change_gold|heal|damage|add_card|add_curse|add_relic", "amount": 10},
        {"type": "add_card|add_curse", "card": "必须来自允许卡牌列表"},
        {"type": "add_relic", "relic": "必须来自允许遗物列表"}
      ]
    }
  ]
}
规则：生成 2 到 4 个选项；每个选项最多 3 个效果；数值效果在 -50 到 50 之间；不要生成战斗、升级或删除卡牌效果；卡牌和遗物只能使用允许列表中的英文内部名称；选项必须有真实取舍，不能全部有利。
""".strip()
    user_prompt = json.dumps(
        {
            "player": state,
            "recent_memory": memory[-10:],
            "allowed_cards": state.get("card_pool", []),
            "allowed_relics": state.get("relic_pool", []),
        },
        ensure_ascii=False,
    )
    return _request_model_json(system_prompt, user_prompt, timeout=30)


def _request_model_json(
    system_prompt: str,
    user_prompt: str,
    timeout: float = 12,
) -> dict[str, Any] | None:
    _load_dotenv()
    config = _runtime_config()
    api_key = config["api_key"]
    if not api_key:
        return None

    base_url = str(config["base_url"]).rstrip("/")
    model = str(config["model"])
    provider_headers = {
        str(key): str(value)
        for key, value in config["headers"].items()
        if isinstance(key, str) and isinstance(value, (str, int, float))
    }
    headers = {"Authorization": f"Bearer {api_key}", **provider_headers}
    if config["api"] == "openai-responses":
        body = {
            "model": model,
            "temperature": 0.7,
            "instructions": f"{system_prompt}\nReturn json only.",
            "input": f"请根据以下内容返回 json：\n{user_prompt}",
            "text": {"format": {"type": "json_object"}},
        }
        endpoints = [_endpoint(base_url, "responses")]
        if not base_url.endswith("/v1"):
            endpoints.append(_endpoint(base_url, "v1/responses"))
        extract = _extract_response_content
    else:
        body = {
            "model": model,
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        endpoints = [_endpoint(base_url, "chat/completions")]
        if not base_url.endswith("/v1"):
            endpoints.append(_endpoint(base_url, "v1/chat/completions"))
        extract = _extract_chat_content

    for endpoint in endpoints:
        content = _post_stream_text(
            endpoint,
            body,
            headers,
            config["api"],
            timeout=timeout,
        )
        if content is None:
            response_data = _post_json(endpoint, body, headers, timeout=timeout)
            if response_data is not None:
                content = extract(response_data)
        if not content:
            continue
        try:
            parsed = json.loads(_clean_json_content(content))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _request_model_text(
    system_prompt: str,
    user_prompt: str,
    timeout: float = 12,
    on_text: Callable[[str], None] | None = None,
) -> str | None:
    _load_dotenv()
    config = _runtime_config()
    api_key = config["api_key"]
    if not api_key:
        return None

    base_url = str(config["base_url"]).rstrip("/")
    model = str(config["model"])
    provider_headers = {
        str(key): str(value)
        for key, value in config["headers"].items()
        if isinstance(key, str) and isinstance(value, (str, int, float))
    }
    headers = {"Authorization": f"Bearer {api_key}", **provider_headers}
    if config["api"] == "openai-responses":
        body = {
            "model": model,
            "temperature": 0.7,
            "instructions": system_prompt,
            "input": user_prompt,
        }
        endpoints = [_endpoint(base_url, "responses")]
        if not base_url.endswith("/v1"):
            endpoints.append(_endpoint(base_url, "v1/responses"))
        extract = _extract_response_content
    else:
        body = {
            "model": model,
            "temperature": 0.7,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        endpoints = [_endpoint(base_url, "chat/completions")]
        if not base_url.endswith("/v1"):
            endpoints.append(_endpoint(base_url, "v1/chat/completions"))
        extract = _extract_chat_content

    for endpoint in endpoints:
        content = _post_stream_text(
            endpoint,
            body,
            headers,
            config["api"],
            on_text=on_text,
            timeout=timeout,
        )
        if content is None:
            response_data = _post_json(endpoint, body, headers, timeout=timeout)
            if response_data is not None:
                content = extract(response_data)
                if content and on_text is not None:
                    on_text(content)
        if content:
            return content.strip()
    return None


def request_turn_host(
    state: dict[str, Any],
    on_text: Callable[[str], None] | None = None,
) -> dict[str, Any] | None:
    system_prompt = """
你是中文 roguelike 文字游戏的地下城主（DM），不是自动玩家。你正在主持玩家的一个战斗回合。
请用自然、沉浸的第二人称口吻叙述现场，像这样：“你面前的下颚虫还剩 27 点生命，它抬起下颚，准备攻击你，预计造成 17 点伤害。你有 3 点能量，手牌正在等待你的决定。”
叙述必须基于玩家状态，准确提到玩家当前生命/能量，以及每个敌人的名称、生命和即将执行的意图；不要编造状态。
不要使用“威胁：”“主持人提示：”这类固定栏目，不要列编号选项，不要替玩家行动。结尾自然地邀请玩家描述行动。
只返回 DM 旁白纯文本，不要 JSON、Markdown、标题或额外解释，长度不超过 360 字。
""".strip()
    user_prompt = json.dumps({"combat": state}, ensure_ascii=False)
    content = _request_model_text(system_prompt, user_prompt, timeout=12, on_text=on_text)
    if not content:
        return None
    return {"narration": content}


def request_action_host(
    before: dict[str, Any],
    after: dict[str, Any],
    player_command: str,
    local_feedback: str = "",
    on_text: Callable[[str], None] | None = None,
) -> str | None:
    system_prompt = """
你是中文 roguelike 文字游戏的 AI 地下城主，负责把一次已经执行完毕的玩家行动整理成一段简洁、连贯的战斗叙事。
只能根据行动前后状态和本地反馈描述结果，不能假设或修改游戏状态，不能提出下一步操作，不能重复完整手牌、敌人列表或操作菜单。
优先说明玩家做了什么，以及生命、格挡、能量、敌人生命或敌人死亡等真正发生的关键变化。
如果前后状态没有变化，明确说明行动没有成功或没有产生效果。只返回中文纯文本，不要 JSON、Markdown、标题或栏目，长度不超过 180 字。
""".strip()
    user_prompt = json.dumps(
        {
            "player_command": player_command,
            "before": before,
            "after": after,
            "local_feedback": local_feedback,
        },
        ensure_ascii=False,
    )
    return _request_model_text(system_prompt, user_prompt, timeout=12, on_text=on_text)


def request_command(state: dict[str, Any], command_text: str) -> dict[str, Any] | None:
    system_prompt = """
你是中文 roguelike 文字游戏的 AI 主持人，只负责把玩家的一句话转换成一个安全的结构化意图。
你不是执行器，不能修改游戏状态。只能返回以下 JSON 之一：
{"kind":"play_card","card":"必须是手牌中的英文内部名称","target":"可选的敌人名称、左边、右边或编号"}
{"kind":"use_potion","potion":"必须是药水栏中的英文内部名称"}
{"kind":"end_turn"}
{"kind":"show_relics"}
{"kind":"show_drawpile"}
{"kind":"show_discardpile"}
{"kind":"show_exhaustpile"}
{"kind":"inspect","query":"卡牌、遗物或药水的英文内部名称"}
{"kind":"unknown"}
只返回 JSON。不能返回多个动作；如果玩家要求连续动作，只转换第一个动作。
""".strip()
    user_prompt = json.dumps(
        {"combat": state, "player_command": command_text}, ensure_ascii=False
    )
    return _request_model_json(system_prompt, user_prompt, timeout=10)


def request_choice(event: dict[str, Any], choice_text: str) -> dict[str, Any] | None:
    system_prompt = """
你是中文 roguelike 文字游戏的 AI 主持人。玩家正在用自然语言表达对当前事件的决定。
请只从提供的事件选项中选择最匹配的一项。不能创造新选项，不能修改效果。
只返回 JSON：{"choice_id":"必须是给定选项中的英文 id"}；如果无法判断，返回 {"choice_id":"unknown"}。
""".strip()
    user_prompt = json.dumps(
        {
            "event": {
                "title": event.get("title"),
                "story": event.get("story"),
                "choices": [
                    {"id": choice.get("id"), "text": choice.get("text")}
                    for choice in event.get("choices", [])
                    if isinstance(choice, dict)
                ],
            },
            "player_decision": choice_text,
        },
        ensure_ascii=False,
    )
    return _request_model_json(system_prompt, user_prompt, timeout=10)

