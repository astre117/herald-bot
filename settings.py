import os

import payments

SETTINGS_PATH = "settings.txt"

# tier: (price, slot range label, last slot of the tier or None)
TIERS = {
    1: (15000, "1-50", 50),
    2: (20000, "51-100", 100),
    3: (25000, "101-150", 150),
    4: (30000, "151-200", 200),
    5: (35000, "201-250", 250),
    6: (40000, "251+", None),
}


def _read():
    values = {}
    if not os.path.exists(SETTINGS_PATH):
        return values
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            values[key.strip()] = val.strip()
    return values


def _int(values, key, default=0):
    try:
        return int(values.get(key, default))
    except ValueError:
        return default


def is_on():
    return _read().get("herald_on", "yes").lower() != "no"


def daily_cap():
    return _int(_read(), "daily_reply_cap", 150)


def tier_link(tier):
    return _read().get(f"link_tier_{tier}", "").strip()


def tier_info():
    v = _read()
    sold = max(0, payments.toolkit_count() + _int(v, "toolkit_count_adjust"))
    tier = min(6, sold // 50 + 1)
    price, slots, last = TIERS[tier]
    return {
        "sold": sold,
        "tier": tier,
        "price": price,
        "slots": slots,
        "left": (last - sold) if last else None,
        "link": tier_link(tier),
    }


def next_link_warning():
    info = tier_info()
    if info["left"] is None:
        return None
    nxt = info["tier"] + 1
    if info["left"] <= 10 and not tier_link(nxt):
        return (
            f"Heads up: only {info['left']} slots left at the current price, "
            f"and link_tier_{nxt} is empty in settings.txt. Create that "
            f"Flutterwave link and add it before the tier fills."
        )
    return None


def status_report():
    v = _read()
    info = tier_info()
    lines = [
        f"Toolkit payments recorded by the bot: {payments.toolkit_count()}",
        f"Adjustment in settings.txt: {_int(v, 'toolkit_count_adjust')}",
        f"Counted as sold: {info['sold']}",
        f"Current tier: {info['tier']} (₦{info['price']:,}, slots {info['slots']})",
    ]
    if info["left"] is not None:
        lines.append(f"Slots left at this price: {info['left']}")
    lines.append(
        "Payment link for this tier: " + ("set" if info["link"] else "MISSING")
    )
    lines.append("Announcing slots left: " + v.get("announce_slots_left", "no"))
    lines.append(
        "Cohort links: full "
        + ("set" if v.get("cohort_link_full", "").strip() else "MISSING")
        + ", split "
        + ("set" if v.get("cohort_link_split", "").strip() else "MISSING")
    )
    full, split = payments._cohort_amounts()
    if full:
        lines.append(
            f"Cohort amounts she watches for: ₦{full:,} full, ₦{split:,} per installment"
        )
    warning = next_link_warning()
    if warning:
        lines.append(warning)
    return "\n".join(lines)


def live_settings_text():
    v = _read()
    info = tier_info()
    lines = [
        f"- Current Starter Toolkit price: ₦{info['price']:,} (launch tier "
        f"{info['tier']}, slots {info['slots']}). Quote only this price."
    ]

    if info["link"]:
        lines.append(
            f"- Payment link for the current tier: {info['link']}\n"
            "  Send it only when the buyer is ready to pay AND you have "
            "already stated the terms plainly (one payment, no installments, "
            "no refunds). Send the link exactly as written."
        )
    else:
        lines.append(
            "- No payment link is available right now. If the buyer is ready "
            "to pay, say you are bringing Coach Create in to sort the "
            "payment, and add the handoff tag."
        )

    proof = v.get("proof_link", "").strip()
    if proof:
        lines.append(
            f"- Proof link with student results: {proof}\n"
            "  When someone asks for proof, results, testimonials or who the "
            "students are, say private details cannot be shared, then send "
            "this link so they can see the results themselves. Send it "
            "exactly as written. Still state the conditions with any result "
            "(contracts are not guaranteed, daily updates are expected, "
            "results depend on effort). Do not send or describe screenshots."
        )
    else:
        lines.append(
            "- No proof link is available. For proof requests, share the "
            "approved results in words, then say Coach Create can send more "
            "and add the handoff tag."
        )

    if v.get("announce_slots_left", "no").lower() == "yes" and info["left"] is not None:
        lines.append(
            f"- Slots left at the current price: {info['left']}. You may "
            "mention this honestly when it is relevant. Never use it to "
            "pressure anyone."
        )
    else:
        lines.append("- Do not say how many slots are left.")

    try:
        cohort = int(v["cohort_price"])
        total = cohort + 15000
        lines.append(
            f"- Current Cohort price: ₦{cohort:,} in full. Installment plan: "
            f"₦{total:,} in two payments of ₦{total // 2:,}."
        )
    except (KeyError, ValueError):
        lines.append(
            "- The Cohort price is unavailable. Say you are confirming it "
            "with Coach Create and add the handoff tag."
        )

    full_link = v.get("cohort_link_full", "").strip()
    split_link = v.get("cohort_link_split", "").strip()
    if full_link or split_link:
        parts = [
            "- Cohort payment links (send only after the buyer says they "
            "want to join and you have explained the options):"
        ]
        if full_link:
            parts.append(f"  Full payment link: {full_link}")
        if split_link:
            parts.append(
                f"  Installment plan link (collects the first payment): {split_link}"
            )
        parts.append(
            "  If they have not said which option they want, briefly explain "
            "the options and ask which they prefer. Then send only the link "
            "they chose, exactly as written. For the installment plan, say "
            "the first payment is made through the link and the second "
            "payment is charged automatically to the same account later, "
            "with a reminder sent before it is charged. Do not state an "
            "exact date. Never change the plan; exceptions go to Coach "
            "Create (handoff tag). Cohort payments are checked by the system "
            "when the buyer sends the email they used at checkout. The "
            "system replies by itself, so never confirm a Cohort payment "
            "yourself and never say access is set up. If someone says they "
            "paid for the Cohort, ask for the email they used at checkout."
        )
        lines.append("\n".join(parts))
    else:
        lines.append(
            "- No Cohort payment links are available. If someone is ready to "
            "join the Cohort, say you are bringing Coach Create in and add "
            "the handoff tag."
        )

    try:
        taken = int(v["cohort_free_seats_taken"])
        left = max(0, 150 - taken)
        lines.append(
            f"- Free Dravonis seats left for new Cohort enrolments: {left} of 150."
        )
    except (KeyError, ValueError):
        lines.append("- Do not state how many free Dravonis seats are left.")

    return (
        "\n\nLIVE SETTINGS (these are current and override any earlier note "
        "in this prompt or the knowledge base saying prices, links or seat "
        "counts are unavailable):\n"
        + "\n".join(lines)
        + "\n- Never describe any figure as verified or verifiable."
        + "\n- After a buyer says they have paid for the toolkit, ask for the "
        "email they used at checkout. The system checks it and sends the "
        "materials automatically. Never send the materials link yourself and "
        "never say a payment is confirmed.\n"
    )
