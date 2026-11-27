"""Boss encounter styles — solo vs escort, and the solo stat budget.

The dungeon rolls a true boss every 5th floor. That boss is one of two styles:

    escort — keeps its template stats and boards with 1–3 normal enemies.
    solo   — boards alone, with a significant stat budget and a second action
             once the party fields 3+ actors.

Solo bosses are curated: the list below is the single source of truth, but a
template may override the choice with ``boss_style: solo`` / ``boss_style:
escort`` in the enemy YAML. The budget is deliberately applied at spawn
(``combat.stats.enemy_stats``) so the HUD, bestiary and combat all see the
same numbers.
"""

# A mix across every level band: a few early bruisers, the named mid-bosses,
# and the high-HP late/endgame bosses. Escort bosses keep the minion pressure.
SOLO_BOSS_KEYS = frozenset({
    # L5–10
    "mountain_troll",
    "infernal_commander",
    "undead_war_behemoth",
    # L11–20
    "greater_abomination",
    "abomination_overlord",
    "dragonkin_overlord",
    "titanic_golem",
    "abyssal_abomination",
    # L21–30
    "giant_king_of_the_peaks",
    "darkness_incarnate",
    "siren_empress",
    "crimson_countess",
    "infernal_empress",
    # L31–40
    "death_bringer",
    "ancient_chronos_golem",
    "dragon_goddess_avatar",
    "omega_clockwork_god",
    "apocalypse_bringer",
    "cosmic_slime_empress",
    "angel_divine_justicar",
    # L41–50
    "goblin_horde_captain",
    "shadow_umbral_sovereign",
    "vampire_blood_sovereign",
    "lizardfolk_scale_tyrant",
    "gnome_omnissiah_prototype",
    "orc_doom_howler",
    "angel_heavenly_choir",
    # L51–60
    "vampire_first_sire",
    "shadow_primordial_dark",
    "angel_archon_of_truth",
    "angel_metatron_voice",
    "dragonkin_apex_of_scales",
    "abomination_first_horror",
    "construct_world_engine",
})

# Solo budget. HP is roughly what the boss + its 3 escorts would have been;
# stats and status resistance cover the lost action economy.
SOLO_HP_MULT = 2.20
SOLO_STAT_MULT = 1.15
SOLO_STATUS_RES_BONUS = 0.30
SOLO_BOSS_ACTIONS = 2
SOLO_ACTION_MIN_PARTY = 3   # player + 2 allies; solo/duo parties keep 1 action


def is_solo_boss(key, template=None):
    """True when *key* should board alone with the solo budget."""
    if template:
        style = str(template.get("boss_style") or "").strip().lower()
        if style == "solo":
            return True
        if style == "escort":
            return False
    return key in SOLO_BOSS_KEYS


def apply_solo_boss_budget(enemy):
    """Mutate a spawned solo boss dict in place. Returns the same dict."""
    enemy["max_hp"] = max(1, int(enemy.get("max_hp", 1) * SOLO_HP_MULT))
    enemy["hp"] = enemy["max_hp"]
    for stat in ("str_mod", "con_mod", "dex_mod", "wis_mod", "ler_mod", "cha_mod"):
        if stat in enemy:
            enemy[stat] = int(enemy[stat] * SOLO_STAT_MULT)
    enemy["status_res"] = min(1.0, enemy.get("status_res", 0.0) + SOLO_STATUS_RES_BONUS)
    enemy["boss_actions"] = SOLO_BOSS_ACTIONS
    enemy["solo_boss"] = True
    return enemy
