"""
tests/test_tools.py

One test per failure mode for each tool, plus happy-path sanity checks.
The search_listings tests run offline; the LLM-backed tests require a valid
GROQ_API_KEY in .env and are skipped automatically if it is missing.

Run with:
    pytest tests/
"""

import os
import sys

import pytest

# Make the project root importable when pytest runs from the tests/ dir.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

needs_key = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping LLM-backed test.",
)


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Impossible query: returns an empty list, never raises.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_is_token_aware():
    # "M" should be allowed to match listings sized "S/M", "M/L", etc.
    results = search_listings("top", size="M", max_price=200)
    assert all("m" in item["size"].lower() for item in results)


# ── suggest_outfit ────────────────────────────────────────────────────────────

@needs_key
def test_suggest_outfit_with_wardrobe():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(out, str) and out.strip()


@needs_key
def test_suggest_outfit_empty_wardrobe():
    # Empty wardrobe must yield useful advice, not a crash or empty string.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    out = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(out, str) and out.strip()


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_fit_card_empty_outfit_returns_error_string():
    # Empty outfit must return a descriptive string, NOT raise.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    card = create_fit_card("", item)
    assert isinstance(card, str)
    assert "without an outfit" in card.lower()


@needs_key
def test_fit_card_varies_for_same_input():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    outfit = "Pair with wide-leg jeans and chunky sneakers."
    a = create_fit_card(outfit, item)
    b = create_fit_card(outfit, item)
    assert a != b  # higher temperature should produce different captions
