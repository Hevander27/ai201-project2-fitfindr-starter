"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _llm(prompt: str, temperature: float = 0.7) -> str:
    """Call the Groq chat model and return the response text."""
    client = _get_groq_client()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()


def _size_matches(requested: str, listing_size: str) -> bool:
    """Case-insensitive, token-aware size match. 'M' matches 'S/M'."""
    req = requested.strip().lower()
    if not req:
        return True
    listing = listing_size.lower()
    # token match on slash/space-separated parts, plus a substring fallback
    tokens = re.split(r"[\s/]+", listing)
    return req in tokens or req in listing


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # 1. Tokenize the search keywords (ignore very short noise words).
    keywords = [w for w in re.findall(r"[a-z0-9]+", description.lower()) if len(w) > 2]

    scored = []
    for item in listings:
        # 2. Hard filters: price ceiling and size.
        if max_price is not None and item["price"] > max_price:
            continue
        if size is not None and not _size_matches(size, item["size"]):
            continue

        # 3. Score by keyword overlap across the searchable text fields.
        haystack = " ".join([
            item["title"],
            item["description"],
            item["category"],
            " ".join(item["style_tags"]),
            " ".join(item["colors"]),
            item["brand"] or "",
        ]).lower()

        score = sum(1 for kw in keywords if kw in haystack)

        # 4. Drop anything with no keyword overlap.
        if score > 0:
            scored.append((score, item))

    # 5. Highest score first; return only the listing dicts.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_desc = (
        f"{new_item['title']} (category: {new_item['category']}, "
        f"style: {', '.join(new_item['style_tags'])}, "
        f"colors: {', '.join(new_item['colors'])})"
    )

    items = wardrobe.get("items", [])

    if not items:
        # Empty-wardrobe fallback: general styling advice, no specific pieces.
        prompt = (
            f"A shopper is considering this secondhand item:\n{item_desc}\n\n"
            "They have not entered any wardrobe yet. In 2-3 sentences, give "
            "general styling advice: what kinds of pieces pair well with it, "
            "what vibe it suits, and how to wear it. Be concrete and friendly."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {it['name']} ({it['category']}; {', '.join(it['style_tags'])})"
            for it in items
        )
        prompt = (
            f"A shopper is considering this secondhand item:\n{item_desc}\n\n"
            f"Their current wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 complete outfit combinations that pair the new item "
            "with SPECIFIC pieces named from their wardrobe above. Keep it to "
            "2-4 sentences total, concrete and conversational."
        )

    try:
        return _llm(prompt, temperature=0.7)
    except Exception as exc:  # noqa: BLE001 - keep the agent usable on LLM failure
        return (
            f"Couldn't generate a styling suggestion right now ({exc}). "
            f"As a starting point, {new_item['title']} works well with simple, "
            "neutral basics that let it stand out."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty or whitespace-only outfit string.
    if not outfit or not outfit.strip():
        return (
            "Can't write a fit card without an outfit suggestion — "
            "no styling details were provided."
        )

    prompt = (
        "Write a short, casual Instagram/TikTok caption (2-4 sentences) for a "
        "thrifted outfit. Sound like a real person posting their fit, NOT a "
        "product description. Mention the item name, price, and platform "
        "naturally (once each). Capture the vibe in specific terms. Emojis ok.\n\n"
        f"Item: {new_item['title']}\n"
        f"Price: ${new_item['price']}\n"
        f"Platform: {new_item['platform']}\n"
        f"Outfit: {outfit}"
    )

    try:
        # Higher temperature so the same item yields different captions.
        return _llm(prompt, temperature=1.0)
    except Exception as exc:  # noqa: BLE001 - return a usable caption on failure
        return (
            f"thrifted this {new_item['title']} off {new_item['platform']} for "
            f"${new_item['price']} and i'm obsessed 🛍️ (caption generator hiccuped: {exc})"
        )
