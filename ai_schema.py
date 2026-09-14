from __future__ import annotations

import re
from typing import Any


ALLOWED_EFFECTS = {
    "change_gold",
    "heal",
    "damage",
    "add_card",
    "upgrade_card",
    "add_relic",
    "add_curse",
}


def _text(value: Any, fallback: str, limit: int) -> str:
    if not isinstance(value, str):
        return fallback
    value = re.sub(r"```(?:json)?|```", "", value).strip()
    value = value.replace("<", "‹").replace(">", "›")
    return value[:limit] or fallback


def _amount(value: Any, minimum: int = -200, maximum: int = 200) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    if result < minimum or result > maximum:
        return None
    return result


def normalize_event(
    payload: Any,
    card_pool: set[str],
    relic_pool: set[str],
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    title = _text(payload.get("title"), "塔中的未知回声", 80)
    story = _text(payload.get("story"), "高塔的墙壁在你耳边低语。", 1000)
    raw_choices = payload.get("choices")
    if not isinstance(raw_choices, list) or not 2 <= len(raw_choices) <= 4:
        return None

    choices: list[dict[str, Any]] = []
    for index, raw_choice in enumerate(raw_choices, start=1):
        if not isinstance(raw_choice, dict):
            return None
        choice_id = _text(raw_choice.get("id"), f"choice_{index}", 40)
        choice_text = _text(raw_choice.get("text"), f"选择 {index}", 180)
        result = _text(raw_choice.get("result"), "你做出了选择。", 500)
        raw_effects = raw_choice.get("effects", [])
        if not isinstance(raw_effects, list) or len(raw_effects) > 3:
            return None

        effects: list[dict[str, Any]] = []
        for raw_effect in raw_effects:
            if not isinstance(raw_effect, dict):
                return None
            effect_type = raw_effect.get("type")
            if effect_type not in ALLOWED_EFFECTS:
                return None

            effect: dict[str, Any] = {"type": effect_type}
            if effect_type in {"change_gold", "heal", "damage"}:
                amount = _amount(raw_effect.get("amount"), -100, 100)
                if amount is None:
                    return None
                effect["amount"] = amount
            elif effect_type in {"add_card", "add_curse"}:
                card_name = raw_effect.get("card")
                if not isinstance(card_name, str) or card_name not in card_pool:
                    return None
                effect["card"] = card_name
            elif effect_type == "add_relic":
                relic_name = raw_effect.get("relic")
                if not isinstance(relic_name, str) or relic_name not in relic_pool:
                    return None
                effect["relic"] = relic_name
            elif effect_type == "upgrade_card":
                effect["amount"] = 1
            effects.append(effect)

        choices.append(
            {
                "id": choice_id,
                "text": choice_text,
                "result": result,
                "effects": effects,
            }
        )

    return {"title": title, "story": story, "choices": choices}


def normalize_turn_briefing(payload: Any) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None
    return {
        "narration": _text(payload.get("narration"), "你站在高塔的战场上，敌人的动作已经显现。轮到你决定下一步了。", 500),
        "threat": _text(payload.get("threat"), "", 180),
        "suggestion": _text(payload.get("suggestion"), "", 220),
    }
