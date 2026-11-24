"""Pick a recipe and a content item for one slot."""
import random
from datetime import datetime, timedelta

from engine.recipes import pool
from engine.types import Plan, Slot


def _planned(events: list[dict], app: str) -> list[dict]:
    return [e for e in events if e.get("event") == "planned" and e.get("app") == app]


def plan_slot(slot: Slot, app: dict, recipes: list[dict], events: list[dict], rng: random.Random,
              cooldown_days: int = 14) -> Plan:
    history = _planned(events, app["slug"])
    choices = recipes
    if len(recipes) > 1 and history:
        choices = [r for r in recipes if r["id"] != history[-1].get("recipe")] or recipes
    recipe = rng.choices(choices, weights=[r["weight"] for r in choices])[0]

    items = pool(app, recipe["content"])
    last_used: dict[str, datetime] = {}
    for e in history:
        last_used[e["combo"]] = datetime.fromisoformat(e["ts"])
    since = slot.at - timedelta(days=cooldown_days)

    def combo(item):
        return f"{recipe['id']}:{item['id']}"

    fresh = [i for i in items if last_used.get(combo(i), since - timedelta(seconds=1)) < since]
    if fresh:
        item = rng.choice(fresh)
    else:  # every item used inside the cooldown: least recently used, never stall
        item = min(items, key=lambda i: last_used[combo(i)])
    return Plan(slot=slot, recipe_id=recipe["id"], content_id=str(item["id"]), combo=combo(item))
