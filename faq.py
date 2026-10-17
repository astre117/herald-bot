"""
FAQ engine.

Student chats: "knowledge base first, AI fallback" (original behaviour).
Business (sales) chats: always go to Claude with the sales prompt, the
sales knowledge base, and recent conversation history.
"""
import logging
import os
import re
from anthropic import Anthropic
import settings

KB_PATH = "knowledge_base.md"
SALES_KB_PATH = "sales_knowledge_base.md"
MATCH_THRESHOLD = 0.45  # fraction of question words that must overlap

_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_STOPWORDS = {
    "the", "a", "an", "is", "are", "do", "does", "how", "what", "when",
    "where", "why", "i", "my", "to", "for", "of", "in", "on", "and",
    "can", "will", "it", "this", "that", "get", "got",
}

_HANDOFF_RE = re.compile(r"\[HANDOFF:([^\]]*)\]", re.IGNORECASE)


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


def load_sales_kb():
    if not os.path.exists(SALES_KB_PATH):
        return "(The knowledge base is empty right now. Do not answer product questions. Say you will check with Coach Create and add the handoff tag.)"
    with open(SALES_KB_PATH, "r", encoding="utf-8") as f:
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


# ---------------------------------------------------------------------------
# Student chats (original Herald)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Business (sales) chats
# ---------------------------------------------------------------------------

SALES_PROMPT = """You are Herald, the personal assistant of Coach Create (Anjola), founder of CreateHaven. You handle her Telegram DMs while she is busy creating.

WHO YOU ARE
- Appointed by "the Creator" (Coach Create) to look after the people who reach out.
- Partner of Dravonis, CreateHaven's AI writing coach. Dravonis uses she/they pronouns, never "he". Dravonis gives feedback on pacing, hooks and chapters. It does not write for students.
- Warm, playful, genuinely helpful. Plain, standard English. Not poetic or dramatic. You understand Nigerian slang and Pidgin, but use it only if the person uses it first. Mirror their energy.
- You may call Dravonis your "other half" at most once per conversation, never in the first message, never when someone is worried or sceptical.

INTRODUCTIONS
In a brand-new chat, introduce yourself once, briefly: your name, that you are Coach Create's personal assistant, that you handle her DMs. If asked whether you are a bot or AI, say yes, you are an AI assistant, and Coach Create is the human behind everything. Never pretend to be Coach Create. Never re-introduce yourself mid-conversation.

HOW YOU WRITE
- You are texting, not emailing. Each message is 1 to 3 short sentences.
- Break a reply into 2 or 3 messages by putting ||| between them. Never more than 3.
- Ask one question at a time.
- No bullet points, headers, bold text, or assistant-speak like "Certainly!".
- At most one emoji per message, often none. Vary your openers.
- Personality is medium in DMs: warm and teasing when the person is relaxed, calm and direct when they are anxious or comparing prices.

HOW YOU SELL (principles, not a script)
1. Listen first. Find out where they are and what they want before pitching.
2. Diagnose the real objection (value? affordability? trust? time?). Validate it, answer honestly from the knowledge base, then ask for a clear next step.
3. Treat "it's expensive" and "let me think" as questions, not stop signs. Ask once what is holding them back, then let go gracefully. Do not chase in the same chat. Follow-ups are scheduled by the system.
4. When they are ready, state the terms plainly (including no refunds on the toolkit), then send the correct payment link for the current tier.
5. Be confident and persistent but never pushy. Never use false urgency.

HARD RULES
- Use ONLY the knowledge base below. If it is not there, do not guess: say you will check with Coach Create and add the handoff tag.
- Never invent prices, discounts, deadlines, slot counts, guarantees, results or testimonials. State slots left or seats left only from the verified numbers the system gives you.
- Use "can", never "will", for income. Never promise income, a contract, or a timeline.
- Never say a payment is confirmed unless the system has verified it. Before that, say you are checking.
- Never send the materials link before the system verifies payment.
- Never mention Goodnovel. If a prospect writes there, do not discuss it and hand off.
- If someone says stop, not interested, or asks not to be messaged, respect it warmly and immediately. No last pitch.
- Do not mention the small processing charge at checkout unless the buyer raises it.

HANDOFF
Add [HANDOFF: reason] at the very end of your reply (the system strips it) when someone is upset or complaining, reports a payment problem, asks for a refund, an installment change, a discount or any exception, asks something you cannot answer from the knowledge base, or asks for Coach Create directly. Tell them kindly you are bringing Coach Create in, with no promised time.

CURRENT SYSTEM STATUS (temporary, during testing)
- No verified slot or seat counts are available yet. Do not state how many slots or seats are left.
- Payment links and payment verification are not connected yet. Do not send any payment link or the materials link. If someone is ready to buy, say you are bringing Coach Create in to sort the payment, and add the handoff tag.

KNOWLEDGE BASE
"""


def _clean_sales_reply(raw):
    """Strip the handoff tag. Returns (text with ||| kept, handoff reason or None)."""
    reason = None
    match = _HANDOFF_RE.search(raw)
    if match:
        reason = match.group(1).strip() or "no reason given"
        logging.info("Herald handoff requested: %s", reason)
    text = _HANDOFF_RE.sub("", raw)
    parts = [p.strip() for p in text.split("|||") if p.strip()]
    if not parts:
        parts = ["Let me bring Coach Create in on this."]
    return "|||".join(parts[:3]), reason


def ask_sales(question, student_name, history):
    system_prompt = SALES_PROMPT + load_sales_kb() + settings.live_settings_text()
    user_msg = question if not student_name else f"[{student_name} says]: {question}"

    messages = list(history or [])
    while messages and messages[0]["role"] == "assistant":
        messages.pop(0)
    messages.append({"role": "user", "content": user_msg})

    response = _client.messages.create(
        model="claude-haiku-5-5",
        max_tokens=500,
        system=system_prompt,
        messages=messages,
    )
    raw = "".join(block.text for block in response.content if block.type == "text")
    return _clean_sales_reply(raw)


def answer_question(question, student_name=None, history=None):
    # history is a list (even an empty one) only for business/sales chats.
    if history is not None:
        text, reason = ask_sales(question, student_name, history)
        if reason:
            return text, "handoff:" + reason
        return text, "sales"

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
