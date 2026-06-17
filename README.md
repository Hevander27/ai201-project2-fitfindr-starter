# FitFindr 🛍️

A multi-tool AI agent that helps you find secondhand clothing and figure out how to wear it. Describe what you want in plain language; FitFindr searches a mock listings dataset, styles the best match against your wardrobe, and writes a shareable caption for the look.

<blockquote class="imgur-embed-pub" lang="en" data-id="a/BTXDC9o"  ><a href="//imgur.com/a/BTXDC9o">FitFindr</a></blockquote><script async src="//s.imgur.com/min/embed.js" charset="utf-8"></script>

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the repo root (never commit it — it's gitignored):

```
GROQ_API_KEY=your_key_here
```

## Run

```bash
python app.py            # launches the Gradio UI (URL printed in terminal)
python agent.py          # CLI happy-path + no-results demo
pytest tests/            # runs the tool tests
```

---

## Tool Inventory

| Tool | Inputs | Output | Purpose |
|------|--------|--------|---------|
| `search_listings` | `description` (str), `size` (str \| None), `max_price` (float \| None) | `list[dict]` of full listing dicts (`id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`), ranked by relevance; `[]` if none match | Find secondhand items matching keywords, size, and a price ceiling |
| `suggest_outfit` | `new_item` (dict), `wardrobe` (dict) | `str` — 2–4 sentence outfit suggestion | Style the found item against the user's wardrobe (or give general advice if the wardrobe is empty) |
| `create_fit_card` | `outfit` (str), `new_item` (dict) | `str` — short shareable caption | Write a casual, social-media-style caption for the look; varies per run |

The documented inputs/outputs match the actual function signatures in `tools.py`.

## How the Planning Loop Works

The loop (`run_agent()` in `agent.py`) is a sequence of **guarded steps** that share one `session` dict, and its behavior changes based on what each tool returns:

1. **Parse** the natural-language query into `description`, `size`, and `max_price` using regex (`_parse_query()`): "under $30" / "$30" → price ceiling, "size M" / a standalone size token → size, remaining words → description.
2. **`search_listings(...)`** runs, and the loop **branches on the result**:
   - **No results (`[]`):** set `session["error"]` with a helpful "relax your filters" message and **return early** — the styling tools are never called with empty input.
   - **Results found:** set `session["selected_item"] = results[0]` (top-ranked) and continue.
3. **`suggest_outfit(selected_item, wardrobe)`** → stored in `session["outfit_suggestion"]`.
4. **`create_fit_card(outfit_suggestion, selected_item)`** → stored in `session["fit_card"]`.
5. **Return** the session.

So an impossible query terminates after step 2 with only `error` set, while a valid query runs all three tools — the agent does not call a fixed sequence regardless of context.

## State Management

A single `session` dict (built by `_new_session()`) is the source of truth for one interaction. Each tool's output is written to a named field, and the next tool reads from that field — the user never re-enters anything:

- `parsed` → search parameters extracted from the query
- `search_results` → list from `search_listings`
- `selected_item` → `search_results[0]`; **this exact dict** is passed into both `suggest_outfit` and `create_fit_card`
- `outfit_suggestion` → string from `suggest_outfit`, passed straight into `create_fit_card`
- `fit_card` → final caption
- `error` → set only on early termination; the UI checks this first

`app.py` reads the completed `session` to populate the three output panels.

## Error Handling (per tool)

- **`search_listings` — no matches:** returns `[]` (never raises). The loop sets `session["error"]`, e.g. *"No listings matched 'designer ballgown', size XXS, under $5. Try raising your price, removing the size filter, or using broader keywords."* and stops before the styling tools.
- **`suggest_outfit` — empty wardrobe:** detects `wardrobe["items"] == []` and switches to a general-advice prompt instead of crashing. Example (tested): for a Y2K baby tee with an empty wardrobe it returned *"This adorable Y2K baby tee is perfect for creating a playful, nostalgic look. Pair it with high-waisted jeans or a flowy …"*. It also catches LLM exceptions and returns a fallback string.
- **`create_fit_card` — missing outfit:** guards an empty/whitespace `outfit` and returns *"Can't write a fit card without an outfit suggestion — no styling details were provided."* (a string, not an exception). LLM errors are caught and produce a simple fallback caption.

## Stretch Feature: Retry Logic with Fallback

If `search_listings` returns no results **but a size filter was applied**, the planning loop automatically retries **once** with the size filter dropped (keeping the keywords and price ceiling). If the retry succeeds, the agent continues normally and records what it loosened in `session["adjustments"]`; the UI prepends a note like *"No exact matches for size XXS — searched all sizes instead."* to the listing panel. If the retry still finds nothing, it falls through to the normal handled-error path. Covered by `test_retry_drops_size_filter_and_reports_it` and `test_retry_still_errors_when_truly_impossible`.

## Spec Reflection

- **How the spec helped:** Writing the tool specs in `planning.md` before coding meant the failure modes were decided up front. Because I had already specified "`search_listings` returns `[]`, the loop sets `error` and returns early," the planning loop's branching logic was obvious to implement — there was no ambiguity about who owns each failure.
- **Where implementation diverged:** The spec assumed clean size strings, but the dataset has messy sizes like `"S/M"`, `"W30 L30"`, and `"US 8"`. I added a token-aware `_size_matches()` helper (split on `/` and spaces, plus a substring fallback) so `"M"` correctly matches `"S/M"` — a detail the original spec glossed over.

## AI Usage

1. **Tool implementations (Milestone 3):** I gave Claude each tool's spec block from `planning.md` (inputs, return value, failure mode) plus the field list from `utils/data_loader.py`, and asked it to implement the functions in `tools.py` using `load_listings()` and the Groq client. I reviewed the generated `search_listings` against the spec and confirmed it filtered by all three parameters and returned `[]` (not an error) on no match; I added the token-aware size matching after noticing the dataset's irregular size strings. Verified with `pytest tests/`.
2. **Planning loop (Milestone 4):** I gave Claude the architecture diagram and the Planning Loop + State Management sections and asked it to implement `run_agent()`. I checked that it branched on the `search_listings` result (early return on `[]`) and stored `selected_item` once so the same dict flowed into both styling tools, then verified the happy path and no-results path with `python agent.py`.
