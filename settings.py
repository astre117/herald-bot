import os

SETTINGS_PATH = "settings.txt"

# tier: (price, slot range)
TIERS = {
    1: (15000, "1-50"),
    2: (20000, "51-100"),
    3: (25000, "101-150"),
    4: (30000, "151-200"),
    5: (35000, "201-250"),
    6: (40000, "251+"),
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


def live_settings_text():
    v = _read()
    lines = []

    try:
        tier = int(v["toolkit_tier"])
        price, slots = TIERS[tier]
        lines.append(
            f"- Current Starter Toolkit price: ₦{price:,} (tier {tier}, "
            f"slots {slots}). Quote this price when asked. Do not say how "
            f"many slots are left."
        )
    except (KeyError, ValueError):
        lines.append(
            "- The toolkit price is unavailable. Say you are confirming it "
            "with Coach Create and add the handoff tag."
        )

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
        "in this prompt or the knowledge base saying prices or seat counts "
        "are unavailable):\n"
        + "\n".join(lines)
        + "\n- Never describe any figure as verified or verifiable."
        + "\n- Still do not send any payment link or materials link. If "
        "someone is ready to buy, say you are bringing Coach Create in and "
        "add the handoff tag.\n"
    )
