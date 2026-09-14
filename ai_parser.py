from __future__ import annotations

import re
from typing import Any

import i18n


COMMAND_ALIASES = {
    "end_turn": ("结束回合", "结束本回合", "回合结束", "end turn", "end"),
    "show_relics": ("查看遗物", "显示遗物", "遗物", "relics", "relic"),
    "show_drawpile": ("查看抽牌堆", "显示抽牌堆", "抽牌堆", "drawpile", "draw pile"),
    "show_discardpile": ("查看弃牌堆", "显示弃牌堆", "弃牌堆", "discardpile", "discard pile"),
    "show_exhaustpile": ("查看消耗牌堆", "显示消耗牌堆", "消耗牌堆", "exhaustpile", "exhaust pile"),
    "save": ("保存", "保存游戏", "存档", "save", "save game"),
}


def _normalize(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\s，。！？、：:；;（）()【】\[\]“”'\"`]+", "", value.strip().lower())


def _contains_command(value: str, aliases: tuple[str, ...]) -> bool:
    normalized = _normalize(value)
    return any(_normalize(alias) in normalized for alias in aliases)


def _find_item(value: str, items: list[dict[str, Any]]) -> tuple[int, dict[str, Any]] | None:
    normalized = _normalize(value)
    if not normalized:
        return None

    candidates: list[tuple[int, int, int, int, dict[str, Any]]] = []
    for index, item in enumerate(items):
        name = item.get("Name")
        if not isinstance(name, str):
            continue
        translated_name = i18n.NAME_TRANSLATIONS.get(name, name)
        source_normalized = _normalize(name)
        translated_normalized = _normalize(translated_name)
        energy = item.get("Energy")
        energy_priority = energy if isinstance(energy, (int, float)) else 999
        if normalized == source_normalized or normalized == translated_normalized:
            candidates.append((0, energy_priority, -len(translated_normalized), index, item))
        elif source_normalized in normalized or translated_normalized in normalized:
            candidates.append((1, energy_priority, -len(translated_normalized), index, item))

    if not candidates:
        return None
    _, _, _, index, item = min(candidates, key=lambda candidate: candidate[:4])
    return index, item


def _target_hint(value: str) -> str | None:
    normalized_value = value.strip()
    action_markers = ("使用", "打出", "出牌", "use", "play")
    for prefix in ("对", "攻击", "target ", "on "):
        if prefix not in normalized_value:
            continue
        target_text = normalized_value.split(prefix, 1)[1]
        for marker in action_markers:
            if marker in target_text:
                target_text = target_text.split(marker, 1)[0]
                break
        target_text = re.sub(r"(?:的)?(?:敌人|敌|目标)$", "", target_text.strip())
        target_text = target_text.strip(" 的地个名")
        if target_text:
            return target_text
    return None


def parse_command(
    value: str,
    hand: list[dict[str, Any]],
    potions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(value, str) or not value.strip():
        return None

    for command, aliases in COMMAND_ALIASES.items():
        if _contains_command(value, aliases):
            return {"kind": command}

    potion_match = _find_item(value, potions)
    if potion_match is not None and any(
        marker in _normalize(value) for marker in ("使用", "喝", "饮用", "use", "drink")
    ):
        index, _ = potion_match
        return {"kind": "use_potion", "index": index}

    card_match = _find_item(value, hand)
    if card_match is not None:
        index, _ = card_match
        command = {"kind": "play_card", "index": index}
        target_hint = _target_hint(value)
        if target_hint is not None:
            command["target_hint"] = target_hint
        return command

    translated_query = i18n.canonicalize_input(value.strip())
    if translated_query != value.strip():
        return {"kind": "inspect", "query": translated_query}
    return {"kind": "unknown", "query": value.strip()}


_TARGET_WORDS = {"一": 0, "二": 1, "三": 2, "四": 3, "1": 0, "2": 1, "3": 2, "4": 3}


def parse_target(value: str, enemies: list[Any]) -> int | None:
    if not isinstance(value, str):
        return None
    normalized = _normalize(value)
    if not normalized:
        return None

    if normalized in {"跳过", "取消", "返回", "skip", "cancel", "back"}:
        return len(enemies)

    number_match = re.search(r"(?:第)?([一二三四1234])(?:个|只|名)?", normalized)
    if number_match:
        target_index = _TARGET_WORDS[number_match.group(1)]
        if target_index < len(enemies):
            return target_index
        if target_index == len(enemies):
            return len(enemies)

    target_text = re.sub(
        r"^(?:请)?(?:攻击|打|选择|指定|瞄准|对|向|把|给|对着|attack|target|on)+",
        "",
        normalized,
    )
    target_text = re.sub(r"(?:的)?(?:敌人|敌|目标)(?:使用|打出|出牌).*$", "", target_text)

    if re.search(r"(?:最)?左(?:边|侧)?|(?:the)?left(?:enemy|target)?", target_text):
        return 0 if enemies else None
    if re.search(r"(?:最)?右(?:边|侧)?|(?:the)?right(?:enemy|target)?", target_text):
        return len(enemies) - 1 if enemies else None

    for index, enemy in enumerate(enemies):
        code_name = getattr(enemy, "codeName", "")
        enemy_name = getattr(enemy, "name", "")
        translated_name = i18n.NAME_TRANSLATIONS.get(code_name, code_name)
        names = {_normalize(code_name), _normalize(enemy_name), _normalize(translated_name)}
        names.discard("")
        if target_text in names or any(name in target_text for name in names):
            return index
    return None


def parse_ai_command(
    payload: dict[str, Any] | None,
    hand: list[dict[str, Any]],
    potions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    allowed_kinds = {
        "end_turn",
        "show_relics",
        "show_drawpile",
        "show_discardpile",
        "show_exhaustpile",
        "inspect",
    }
    if kind in allowed_kinds:
        if kind == "inspect":
            query = payload.get("query")
            return {"kind": kind, "query": query} if isinstance(query, str) and query.strip() else None
        return {"kind": kind}

    if kind == "play_card":
        card = payload.get("card")
        if not isinstance(card, str):
            return None
        match = _find_item(card, hand)
        if match is None:
            return None
        index, _ = match
        command = {"kind": "play_card", "index": index}
        target = payload.get("target")
        if isinstance(target, str) and target.strip():
            command["target_hint"] = target.strip()
        return command

    if kind == "use_potion":
        potion = payload.get("potion")
        if not isinstance(potion, str):
            return None
        match = _find_item(potion, potions)
        if match is None:
            return None
        index, _ = match
        return {"kind": "use_potion", "index": index}
    return None
