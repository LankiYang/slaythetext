from __future__ import annotations

import difflib
import os
from typing import Any

import ai_memory
import ai_service
from ai_schema import normalize_event, normalize_turn_briefing


OFFLINE_EVENTS = (
    {
        "title": "裂缝中的火光",
        "story": "你在高塔裂缝中发现一盏不会熄灭的灯。火光里传来低语：力量可以治愈伤口，但每一次交换都需要代价。",
        "choices": (
            {
                "id": "touch_flame",
                "text": "伸手触碰火焰，接受它的温度",
                "result": "火焰没有灼伤你，反而温暖了你的血液。",
                "effects": [{"type": "heal", "amount": 8}],
            },
            {
                "id": "feed_flame",
                "text": "投入 30 金币，让火焰更明亮",
                "result": "火焰吞下金币，吐出一张记载着战技的卡牌。",
                "effects": [
                    {"type": "change_gold", "amount": -30},
                    {"type": "add_card", "card": "Strike"},
                ],
            },
            {
                "id": "walk_away",
                "text": "不理会低语，继续赶路",
                "result": "火光在你身后熄灭，裂缝重新归于寂静。",
                "effects": [],
            },
        ),
    },
    {
        "title": "会说话的书架",
        "story": "一排书架从墙壁中长出，书页像翅膀一样翻动。最上层的一本书向你承诺知识，却警告你：读懂它，就会忘记一些别的东西。",
        "choices": (
            {
                "id": "read_book",
                "text": "阅读发光的书页",
                "result": "陌生的战术涌入脑海，你获得了一张卡牌。",
                "effects": [{"type": "add_card", "card": "Defend"}],
            },
            {
                "id": "burn_books",
                "text": "烧掉书架，趁乱搜刮金币",
                "result": "火焰吞没了书架，也留下了一小袋金币。",
                "effects": [
                    {"type": "damage", "amount": 5},
                    {"type": "change_gold", "amount": 45},
                ],
            },
            {
                "id": "close_books",
                "text": "合上书页，拒绝未知知识",
                "result": "书架无声地缩回墙中，你对自己的谨慎感到满意。",
                "effects": [],
            },
        ),
    },
    {
        "title": "倒悬的商人",
        "story": "一个倒挂在天花板上的商人拦住了你。他的货物都装在会呼吸的袋子里，并保证其中一件能改变你的冒险。",
        "choices": (
            {
                "id": "buy_power",
                "text": "支付 40 金币，购买一件奇物",
                "result": "袋子吐出一枚古老遗物，商人满意地消失了。",
                "effects": [
                    {"type": "change_gold", "amount": -40},
                    {"type": "add_relic", "relic": "Anchor"},
                ],
            },
            {
                "id": "threaten_merchant",
                "text": "威胁商人，索要一张卡牌",
                "result": "商人尖叫着逃走，只来得及丢下一张卡牌。",
                "effects": [
                    {"type": "damage", "amount": 8},
                    {"type": "add_card", "card": "Bash"},
                ],
            },
            {
                "id": "leave_merchant",
                "text": "礼貌道别，什么也不买",
                "result": "商人嘟囔着重新倒挂回去，你继续向高处前进。",
                "effects": [],
            },
        ),
    },
)


def enabled() -> bool:
    ai_service._load_dotenv()
    return os.getenv("SLAYTHETEXT_AI_EVENTS", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _offline_event(state: dict[str, Any]) -> dict[str, Any]:
    index = (int(state.get("floor", 0)) + int(state.get("encounter", 0))) % len(OFFLINE_EVENTS)
    template = OFFLINE_EVENTS[index]
    card_pool = state.get("card_pool", [])
    relic_pool = state.get("relic_pool", [])
    raw_choices = []
    for choice in template["choices"]:
        effects = []
        for effect in choice["effects"]:
            effect = effect.copy()
            if effect.get("type") in {"add_card", "add_curse"}:
                effect["card"] = effect.get("card") if effect.get("card") in card_pool else (card_pool[0] if card_pool else None)
            elif effect.get("type") == "add_relic":
                effect["relic"] = effect.get("relic") if effect.get("relic") in relic_pool else (relic_pool[0] if relic_pool else None)
            if effect.get("card") or effect.get("relic") or effect.get("type") not in {"add_card", "add_curse", "add_relic"}:
                effects.append(effect)
        raw_choices.append({**choice, "effects": effects})
    return {"title": template["title"], "story": template["story"], "choices": raw_choices}


def generate_event(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    card_pool = set(state.get("card_pool", []))
    relic_pool = set(state.get("relic_pool", []))
    if enabled():
        payload = ai_service.request_event(state, ai_memory.load())
        normalized = normalize_event(payload, card_pool, relic_pool)
        if normalized is not None:
            return normalized, "online"
    offline = _offline_event(state)
    normalized = normalize_event(offline, card_pool, relic_pool)
    if normalized is None:
        raise RuntimeError("无法创建 AI 事件")
    return normalized, "offline"


def resolve_choice(event: dict[str, Any], value: str) -> dict[str, Any] | None:
    normalized = value.strip().lower()
    choices = event.get("choices", [])
    if normalized.isdigit():
        index = int(normalized) - 1
        return choices[index] if index in range(len(choices)) else None

    number_words = {"一": 0, "二": 1, "三": 2, "四": 3, "1": 0, "2": 1, "3": 2, "4": 3}
    if normalized in number_words:
        index = number_words[normalized]
        return choices[index] if index in range(len(choices)) else None

    for choice in choices:
        choice_id = str(choice.get("id", "")).lower()
        choice_text = str(choice.get("text", "")).lower()
        if normalized == choice_id or normalized == choice_text:
            return choice
        if normalized and (normalized in choice_id or normalized in choice_text):
            return choice
        if choice_text and choice_text in normalized:
            return choice

    candidates = []
    for choice in choices:
        ratio = difflib.SequenceMatcher(None, normalized, str(choice.get("text", "")).lower()).ratio()
        candidates.append((ratio, choice))
    if candidates:
        ratio, choice = max(candidates, key=lambda item: item[0])
        if ratio >= 0.35:
            return choice
    return None


def has_online_provider() -> bool:
    return ai_service.online_available()


def _offline_turn_briefing(state: dict[str, Any]) -> dict[str, str]:
    turn = state.get("turn", 0)
    enemies = state.get("enemies", [])
    enemy_texts = []
    for enemy in enemies:
        if not isinstance(enemy, dict):
            continue
        name = str(enemy.get("name", "敌人"))
        health = enemy.get("health", "?")
        max_health = enemy.get("max_health", "?")
        intent = str(enemy.get("intent", "未知行动"))
        enemy_texts.append(f"{name} 还剩 {health}/{max_health} 点生命，{intent}")
    if enemy_texts:
        if len(enemy_texts) == 1:
            enemy_scene = f"你面前是 {enemy_texts[0]}"
        else:
            enemy_scene = "你面前有 " + "；".join(enemy_texts)
    else:
        enemy_scene = "战场上暂时没有敌人"
    hand = state.get("hand", [])
    playable = [str(card.get("name")) for card in hand if isinstance(card, dict) and card.get("name")]
    card_text = "、".join(playable[:4]) or "没有可见手牌"
    narration = (
        f"第 {turn} 回合，你有 {state.get('health', '?')}/{state.get('max_health', '?')} 点生命、"
        f"{state.get('energy', '?')} 点能量。{enemy_scene}。"
        f"你手中的牌是 {card_text}。轮到你行动了，直接告诉我你想做什么。"
    )
    return {"narration": narration, "threat": "", "suggestion": ""}


def generate_turn_briefing(
    state: dict[str, Any],
    on_text=None,
) -> tuple[dict[str, str], str]:
    if enabled():
        payload = ai_service.request_turn_host(state, on_text=on_text)
        normalized = normalize_turn_briefing(payload)
        if normalized is not None:
            return normalized, "online"
    return _offline_turn_briefing(state), "offline"


def _offline_action_summary(
    before: dict[str, Any],
    after: dict[str, Any],
    player_command: str,
) -> str:
    before_health = before.get("health")
    after_health = after.get("health")
    before_block = before.get("block")
    after_block = after.get("block")
    before_energy = before.get("energy")
    after_energy = after.get("energy")
    changes = []
    for label, old, new in (
        ("生命", before_health, after_health),
        ("格挡", before_block, after_block),
        ("能量", before_energy, after_energy),
    ):
        if old != new and new is not None:
            changes.append(f"{label} {new}")

    before_enemies = {enemy.get("name"): enemy.get("health") for enemy in before.get("enemies", []) if isinstance(enemy, dict)}
    after_enemies = {enemy.get("name"): enemy.get("health") for enemy in after.get("enemies", []) if isinstance(enemy, dict)}
    defeated = [name for name in before_enemies if name not in after_enemies]
    if defeated:
        changes.append("击败了" + "、".join(str(name) for name in defeated))
    if changes:
        return f"你执行了“{player_command}”。" + "，".join(changes) + "。"
    return f"你执行了“{player_command}”，但这次行动没有改变战场状态。"


def generate_action_summary(
    before: dict[str, Any],
    after: dict[str, Any],
    player_command: str,
    local_feedback: str = "",
    on_text=None,
) -> tuple[str, str]:
    if enabled() and ai_service.online_available():
        content = ai_service.request_action_host(
            before,
            after,
            player_command,
            local_feedback,
            on_text=on_text,
        )
        if content:
            return content, "online"
    return _offline_action_summary(before, after, player_command), "offline"


def interpret_command(state: dict[str, Any], command_text: str) -> dict[str, Any] | None:
    if not enabled():
        return None
    return ai_service.request_command(state, command_text)


def interpret_choice(event: dict[str, Any], value: str) -> dict[str, Any] | None:
    if not enabled():
        return None
    return ai_service.request_choice(event, value)


def resolve_ai_choice(event: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    choice_id = payload.get("choice_id")
    if not isinstance(choice_id, str) or choice_id == "unknown":
        return None
    for choice in event.get("choices", []):
        if isinstance(choice, dict) and choice.get("id") == choice_id:
            return choice
    return None


def remember_choice(event: dict[str, Any], choice: dict[str, Any]) -> None:
    ai_memory.remember(
        str(event.get("title", "未知事件")),
        str(choice.get("id", "choice")),
        str(choice.get("text", "")),
        str(choice.get("result", "")),
    )
