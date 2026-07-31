"""
Blitz Culture — Designer Agent Orchestrator
----------------------------------------------
Takes a "trigger" (headline, article, stat block, or a rankings self-check),
asks Claude to decide whether it's post-worthy and how it should look, then
renders the chosen guided layout to a PNG.

SETUP:
  pip install anthropic python-dotenv playwright
  playwright install chromium
  Add ANTHROPIC_API_KEY=... to your .env file
"""

import os
import json
import time
from anthropic import Anthropic
from dotenv import load_dotenv

from html_templates import LAYOUTS
from render_html import render_html_to_png

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

with open("system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()


def run_agent(trigger: dict, rankings_state: dict) -> dict:
    """
    trigger: {"type": "headline" | "article" | "stat_block" | "rankings_check",
              "content": str}
    rankings_state: your persisted current rankings (any JSON-serializable shape)

    Returns the parsed decision dict from Claude.
    """
    user_input = {
        "trigger": trigger,
        "current_rankings_state": rankings_state,
    }

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(user_input)}],
    )

    raw_text = response.content[0].text
    # Defensive: strip accidental markdown fences if the model adds them
    cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    decision = json.loads(cleaned)
    return decision


def render_decision(decision: dict, output_dir: str = "output") -> str | None:
    """Takes a decision dict with action == 'post' and renders its graphic_spec."""
    if decision.get("action") != "post":
        print("No action taken:", decision.get("reasoning_summary"))
        return None

    spec = decision["graphic_spec"]
    key = (spec["template"], spec["layout_variant"])
    if key not in LAYOUTS:
        raise ValueError(f"Unknown template/variant combo: {key}")

    layout_fn = LAYOUTS[key]

    # Each layout function has a slightly different signature — call accordingly
    if spec["template"] == "player_spotlight":
        html = layout_fn(spec["title"], spec.get("primary_player", ""), spec["data_points"])
    else:
        html = layout_fn(spec["title"], spec["data_points"])

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"post_{int(time.time())}.png")
    render_html_to_png(html, output_path)
    return output_path


if __name__ == "__main__":
    # Example: a headline trigger, with a placeholder rankings state
    example_trigger = {
        "type": "headline",
        "content": "Super Bowl MVP Kenneth Walker III has agreed to sign with the Kansas City Chiefs, a source told ESPN's Adam Schefter. Walker is receiving a three-year deal with a $43.05 million base value and $28.7 million fully guaranteed, sources told ESPN's Brady Henderson.",
    }
    example_rankings = {"RB": [{"rank": 1, "name": "Example Player", "team": "XYZ"}]}

    decision = run_agent(example_trigger, example_rankings)
    print(json.dumps(decision, indent=2))

    path = render_decision(decision)
    if path:
        print(f"\nGraphic ready at: {path}")
        print("Caption:", decision.get("caption"))
        print("Hashtags:", " ".join(decision.get("hashtags", [])))
        print("Needs approval:", decision.get("needs_approval"))
