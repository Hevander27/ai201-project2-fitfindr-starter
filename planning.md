# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the 40-item mock listings dataset for secondhand pieces that match the user's keywords, optional size, and optional price ceiling, and returns them ranked by how well they match.

**Input parameters:**
- `description` (str): Free-text keywords describing the desired item, e.g. `"vintage graphic tee"`. Used for keyword-overlap scoring against each listing's title, description, style_tags, category, colors, and brand.
- `size` (str | None): A size string to filter by (e.g. `"M"`, `"US 8"`). Matching is case-insensitive and token-aware, so `"M"` matches a listing sized `"S/M"`. `None` skips size filtering.
- `max_price` (float | None): Inclusive price ceiling. A listing qualifies only if `price <= max_price`. `None` skips price filtering.

**What it returns:**
A `list[dict]` of full listing dictionaries (each with `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`), sorted by relevance score (best match first). Listings with a keyword score of 0 are dropped.

**What happens if it fails or returns nothing:**
Returns an empty list `[]` — never raises. The agent detects the empty list, sets `session["error"]` with a message telling the user what to relax (price, size, or keywords), and returns early without calling the styling tools.

---

### Tool 2: suggest_outfit

**What it does:**
Uses the Groq LLM to style the found item against the user's wardrobe, returning one or two concrete outfit combinations that name specific wardrobe pieces.

**Input parameters:**
- `new_item` (dict): The selected listing dict from `search_listings` (the item being considered).
- `wardrobe` (dict): A wardrobe dict with an `items` key (list of `{id, name, category, colors, style_tags, notes}`). May be empty.

**What it returns:**
A non-empty `str` of styling suggestions. With a populated wardrobe it references items by name; with an empty wardrobe it returns general styling advice (what to pair, what vibe it suits) instead.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, it falls back to a general-advice prompt rather than crashing. If the LLM call raises, it catches the exception and returns a plain-language fallback string so the agent can still continue.

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, casual, shareable caption (the kind you'd post with an OOTD photo) for the found item and the suggested outfit, using a higher LLM temperature so outputs vary.

**Input parameters:**
- `outfit` (str): The outfit suggestion string produced by `suggest_outfit`.
- `new_item` (dict): The selected listing dict, used to weave in the item name, price, and platform.

**What it returns:**
A 2–4 sentence `str` caption that mentions the item, price, and platform naturally and captures the outfit vibe. Varies across runs for the same input.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, it returns a descriptive error string (not an exception). If the LLM call raises, it catches it and returns a simple fallback caption built from the item fields.

---

### Additional Tools (if any)

None for the required build. (Stretch candidates if pursued: `estimate_fair_price`, `load_style_profile`.)

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is a sequence of guarded steps driven by what each tool returns, sharing one `session` dict:

1. **Parse** the natural-language query into `description`, `size`, and `max_price` (regex for `$NN` / "under $NN" prices and "size X" / standalone size tokens; remaining words become the description). Store in `session["parsed"]`.
2. **Call `search_listings(description, size, max_price)`** and store `session["search_results"]`.
   - **Branch C (retry, evaluated first) — `results == []` and a size filter was applied (`parsed["size"]` is not None):** before giving up, retry `search_listings` **once** with `size=None` (keeping the same `description` and `max_price`). Record what was loosened in `session["adjustments"]` (e.g. *"No exact matches for size M — searched all sizes instead."*). If the retry returns results, proceed as Branch B; if it still returns `[]`, fall through to Branch A.
   - **Branch A — `results == []` (after any retry):** set `session["error"]` to a helpful relax-your-filters message and `return session` immediately. `suggest_outfit` and `create_fit_card` are **not** called.
   - **Branch B — `results` non-empty:** set `session["selected_item"] = results[0]` (top-ranked) and continue.

3. **Call `suggest_outfit(selected_item, wardrobe)`**, store `session["outfit_suggestion"]`. This tool internally branches on whether the wardrobe is empty (general advice vs. wardrobe-specific outfits).
4. **Call `create_fit_card(outfit_suggestion, selected_item)`**, store `session["fit_card"]`. This tool internally branches on whether the outfit string is empty.
5. **Return** the completed `session`.

The agent's behavior changes with input: an impossible query terminates at step 2 with only `error` set; a valid query runs all three tools. It "knows it's done" when it reaches step 5 (success) or hits the early return in Branch A (handled failure).

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict (created by `_new_session()` in `agent.py`) is the single source of truth for one interaction. The output of each tool is written into a named field, and the next tool reads from that field rather than from the user:

- `query` / `parsed` — original query and extracted `description`, `size`, `max_price`.
- `search_results` — list returned by `search_listings`.
- `selected_item` — `search_results[0]`; this exact dict is passed into both `suggest_outfit` and `create_fit_card` (no re-entry by the user).
- `outfit_suggestion` — string from `suggest_outfit`; passed directly into `create_fit_card`.
- `fit_card` — final caption string.
- `error` — set only when the interaction ends early; the UI checks this first.
- `adjustments` — set only when the retry fallback loosened a filter (stretch feature); the UI prepends it to the listing panel so the user knows what changed.

The data flows in-memory within one `run_agent()` call; nothing is re-typed by the user between steps. `app.py` reads the final `session` to populate the three UI panels.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Returns `[]`. The planning loop sets `session["error"]` to: *"No listings matched 'X'. Try raising your price, removing the size filter, or using broader keywords."* and stops before the styling tools — no empty input is forwarded. |
| suggest_outfit | Wardrobe is empty (`items == []`) | Detects the empty list and switches to a general-styling-advice prompt, returning useful tips (what to pair, what vibe it suits) instead of crashing or returning an empty string. Also catches LLM errors and returns a plain fallback string. |
| create_fit_card | Outfit input is missing or incomplete | Guards against an empty/whitespace `outfit` and returns a descriptive error string: *"Can't write a fit card without an outfit suggestion."* Also catches LLM errors and returns a simple caption built from the item fields. |
| search_listings (stretch: retry) | No results, but a size filter was applied | Before erroring, the loop automatically retries once with the size filter dropped, records the change in `session["adjustments"]`, and the UI tells the user what was loosened (e.g. *"No exact matches for size M — searched all sizes instead."*). |

---

## Architecture

User query
    │
    ▼
Planning Loop ───────────────────────────────────────────┐
    │                                                    │
    ├─► search_listings(description, size, max_price)    │
    │       │ results=[]                                 │
    │       ├──► [ERROR] "No listings found..." → return │
    │       │                                            │
    │       │ results=[item, ...]                        │
    │       ▼                                            │
    │   Session: selected_item = results[0]              │
    │       │                                            │
    ├─► suggest_outfit(selected_item, wardrobe)          │
    │       │                                            │
    │   Session: outfit_suggestion = "..."               │
    │       │                                            │
    └─► create_fit_card(outfit_suggestion, selected_item)│
            │                                            │
        Session: fit_card = "..."                        │
            │                                            └─ error path returns here
            ▼
        Return session

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
Tool used: Claude (Claude Code). Input: one tool spec block at a time from the **Tools** section above (inputs, return value, failure mode) plus the field list from `utils/data_loader.py`. Expected output: each function implemented in `tools.py` using `load_listings()` and the Groq client. Verification before trusting: confirm `search_listings` filters by all three parameters and returns `[]` (not an error) on no match; confirm `suggest_outfit` branches on an empty wardrobe; confirm `create_fit_card` guards an empty outfit and uses a higher temperature. Then run `pytest tests/` (one test per failure mode) and 3 manual queries.

**Milestone 4 — Planning loop and state management:**
Tool used: Claude (Claude Code). Input: the **Architecture** diagram plus the **Planning Loop** and **State Management** sections above. Expected output: `run_agent()` in `agent.py` implementing the guarded sequence and writing every result into the `session` dict. Verification before trusting: confirm it branches on the `search_listings` result (early return on `[]`), confirm it never calls `suggest_outfit`/`create_fit_card` when search is empty, and confirm `selected_item` passed into the styling tools is the same dict stored in the session (print and compare). Then run `python agent.py` for both the happy path and the no-results path.

---

## A Complete Interaction (Step by Step)

FitFindr is an AI agent that helps a user find secondhand clothing and figure out how to wear it. A natural-language request triggers `search_listings`, which filters the mock dataset by description, size, and price; the top match then flows into `suggest_outfit`, which pairs it with the user's wardrobe, and finally into `create_fit_card`, which writes a shareable caption for the look. If `search_listings` returns no matches, the agent stops there and tells the user what to adjust instead of passing empty input into the styling tools, and the outfit and fit-card tools each fall back to general advice or an error message rather than crashing when their input is missing.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
```
search_listings("vintage graphic tee", size="M", max_price=30.0) returns 3 matching listings sorted by relevance. FitFindr picks the top result: "Faded Band Tee — $22, Depop, Good condition." 
```

**Step 2:**
```
suggest_outfit(new_item=<band tee>, wardrobe=<user's wardrobe>) returns: "Pair this with your wide-leg jeans and platform Docs for a classic 90s grunge look. Roll the sleeves once and tuck the front corner slightly for shape." 
```

**Final output to user:**
```
create_fit_card(outfit=<suggestion>, new_item=<band tee>) returns: "thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories" 
```

**Error path:**
```
If search_listings returns nothing, FitFindr tells the user what to try differently and stops — it does not call suggest_outfit with empty input. 
```