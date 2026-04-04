"""Stateless helpers (ranks, MMR math, name parsing) — safe to unit test without Discord."""

# ─────────────────────────────────────────────
# HALO REACH RANK SYSTEM
# ─────────────────────────────────────────────
HALO_RANKS = [
    (95.5, "Inheritor",       "021_Inheritor"),
    (91.0, "Reclaimer",       "020_Reclaimer"),
    (86.5, "Forerunner",      "019_Forerunner"),
    (82.0, "Nova",            "018_Nova"),
    (77.5, "Eclipse",         "017_Eclipse"),
    (73.0, "Noble",           "016_Noble"),
    (68.5, "Mythic",          "015_Mythic"),
    (64.0, "Legend",          "014_Legend"),
    (59.5, "Hero",            "013_Hero"),
    (55.0, "Field_Marshall",  "012_Field_Marshall"),
    (50.5, "General",         "011_General"),
    (46.0, "Brigadier",       "010_Brigadier"),
    (41.5, "Colonel",         "009_Colonel"),
    (37.0, "Commander",       "008_Commander"),
    (32.5, "Lt_Colonel",      "007_Lt_Colonel"),
    (28.0, "Major",           "006_Major"),
    (23.5, "Captain",         "005_Captain"),
    (19.0, "Warrant_Officer", "004_Warrant_Officer"),
    (14.5, "Sergeant",        "003_Sergeant"),
    (10.0, "Corporal",        "002_Corporal"),
    (5.0,  "Private",         "001_Private"),
    (0.0,  "Recruit",         "000_Recruit"),
]


def halo_rank(mmr: float) -> tuple:
    for threshold, name, ename in HALO_RANKS:
        if mmr >= threshold:
            return name, ename
    return "Recruit", "000_Recruit"


def canonical_name(raw: str) -> str:
    return raw.split("(")[0].strip()


WEIGHTS = {"kd": 0.30, "points": 0.25, "obj_time": 0.25, "assists": 0.15, "captures": 0.05}


def normalise(values: list) -> list:
    mn, mx = min(values), max(values)
    if mx == mn:
        return [50.0] * len(values)
    return [(v - mn) / (mx - mn) * 100 for v in values]


def calculate_mmr(players: list) -> list:
    keys = list(WEIGHTS.keys())
    normed = {k: normalise([p[k] for p in players]) for k in keys}
    for i, p in enumerate(players):
        p["mmr"] = round(sum(normed[k][i] * WEIGHTS[k] for k in keys), 1)
    return players


def parse_names(raw: str) -> list:
    parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
    return [p for p in parts if p]
