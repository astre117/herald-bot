"""
FAQ engine.

Strategy: "knowledge base first, AI fallback"
1. Parse knowledge_base.md into Q/A pairs.
2. Score the incoming question against each stored question using simple
   word-overlap similarity (fast, free, no API call, and predictable).
3. If the best match clears a similarity threshold, answer with the stored
   text verbatim (optionally lightly reworded by Claude for tone).
4. Otherwise, fall back to Claude, but still hand it the full knowledge
   base as context so it stays grounded in real cohort facts and doesn't
   invent policy details.
"""
import os
import re
from anthropic import Anthropic

KB_PATH = "knowledge_base.md"
MATCH_THRESHOLD = 0.45  # fraction of question words that must overlap

_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_STOPWORDS = {
    "the", "a", "an", "is", "are", "do", "does", "how", "what", "when",
    "where", "why", "i", "my", "to", "for", "of", "in", "on", "and",
    "can", "will", "it", "this", "that", "get", "got",
}


def _tokenize(text):
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def load_kb_pairs():
    """Returns a list of (question, answer) tuples from knowledge_base.md."""
    if not os.path.exists(KB_PATH):
        return []
    with open(KB_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    pairs = []
    current_q, current_a_lines = None, []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("Q:"):
            if current_q is not None:
                pairs.append((current_q, " ".join(current_a_lines).strip()))
            current_q = stripped[2:].strip()
            current_a_lines = []
        elif stripped.startswith("A:"):
            current_a_lines.append(stripped[2:].strip())
    if current_q is not None:
        pairs.append((current_q, " ".join(current_a_lines).strip()))
    return pairs


def load_kb_raw():
    if not os.path.exists(KB_PATH):
        return ""
    with open(KB_PATH, "r", encoding="utf-8") as f:
        return f.read()


def find_best_match(question, pairs):
    q_tokens = _tokenize(question)
    if not q_tokens:
        return None, 0.0

    best_pair, best_score = None, 0.0
    for kb_q, kb_a in pairs:
        kb_tokens = _tokenize(kb_q)
        if not kb_tokens:
            continue
        overlap = len(q_tokens & kb_tokens)
        score = overlap / len(q_tokens)
        if score > best_score:
            best_score = score
            best_pair = (kb_q, kb_a)
    return best_pair, best_score


def ask_ai_fallback(question, kb_context, student_name=None):
    system_prompt = (
        "You are Herald, the guide and community presence for CreateHaven's "
        "writing cohort on Telegram. You're warm, a little playful, and "
        "genuinely dedicated to helping every student find their footing — "
        "you take real pride in guiding people onto the right path, and "
        "you're intelligent enough to handle nuance yourself rather than "
        "escalating everything to a human.\n\n"
        "Lore/character notes: you were appointed by 'the Creator' (the "
        "founder of CreateHaven) to watch over this cohort. Dravonis is "
        "CreateHaven's AI writing tool and, in your telling, your other "
        "half or partner — Dravonis shapes the words, you shape everything "
        "around them. Dravonis speaks in a more poetic, riddling style; "
        "you speak plain, standard English. You can reference the Creator "
        "and Dravonis warmly and a little playfully when it fits naturally "
        "— don't force it into every message. You understand Nigerian "
        "slang and slang in general even though you don't necessarily lean "
        "on it yourself, so never act confused by casual or "
        "Nigerian-inflected phrasing.\n\n"
        "You're conversational, not just a FAQ box — students may vent, "
        "joke around, or just chat, not only ask logistics questions. Meet "
        "them where they are: encourage, banter a little, or just listen, "
        "as the moment calls for. Students are learning to write "
        "serialized fiction for platforms like Webnovel and PocketFM.\n\n"
        "Here is the cohort's known knowledge base. Prioritize this "
        "information when it's relevant, and don't contradict it:\n\n"
        f"{kb_context}\n\n"
        "For anything outside the knowledge base — general writing craft, "
        "platform strategy, encouragement, casual conversation — answer "
        "helpfully and in character as Herald. Keep responses "
        "conversational and concise — a few sentences, not an essay. If "
        "you genuinely don't know something specific to this cohort (like "
        "exact dates or prices you weren't given), say so plainly and "
        "suggest they ping an admin rather than guessing."
    )
    user_msg = question if not student_name else f"[{student_name} says]: {question}"

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def answer_question(question, student_name=None):
    pairs = load_kb_pairs()
    best_pair, score = find_best_match(question, pairs)

    if best_pair and score >= MATCH_THRESHOLD:
        return best_pair[1], "kb"

    kb_context = load_kb_raw()
    answer = ask_ai_fallback(question, kb_context, student_name)
    return answer, "ai"


def celebrate_win(win_text, student_name=None):
    """Called whenever someone posts in the Wins & Testimonials topic.
    Generates a short, specific, in-character celebration from Herald —
    reacting to what they actually wrote, not a generic canned line."""
    system_prompt = (
        "You are Herald, the warm and playful guide of CreateHaven's "
        "writing cohort. A student just posted a win or testimonial in the "
        "community's Wins & Testimonials topic. React to it like a proud, "
        "genuinely excited guide would — specific to what they actually "
        "shared, not generic. Keep it short: one or two sentences, "
        "celebratory, with real warmth. You can reference the Creator or "
        "Dravonis if it fits naturally, but don't force it. No essay, no "
        "bullet points — just a genuine, hype reaction."
    )
    user_msg = win_text if not student_name else f"[{student_name} posted]: {win_text}"

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )
    return "".join(block.text for block in response.content if block.type == "text")
