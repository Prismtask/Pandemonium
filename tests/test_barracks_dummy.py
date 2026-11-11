# tests/test_barracks_dummy.py — regression for the training-dummy reset path.
#
# 2026-11-11 health check found a NameError: "Reset to Defaults" referenced
# DEFAULT_DUMMY_CONFIG, which was imported only inside _dummy_spar_flow().
# Also covers the nested-dict aliasing that would otherwise let resistance
# edits pollute the module-level defaults.
from pandemonium.combat.dummy import (
    DEFAULT_DUMMY_CONFIG,
    copy_default_dummy_config,
)
from pandemonium.facilities import barracks


class _ScriptedTerm:
    """Minimal term stub: returns scripted menu choices, records output."""

    def __init__(self, choices):
        self._choices = list(choices)
        self.messages = []
        self.pause_count = 0

    def menu(self, *args, **kwargs):
        return self._choices.pop(0)

    def print(self, text=""):
        self.messages.append(str(text))

    def pause(self, *args, **kwargs):
        self.pause_count += 1

    def clear(self):
        pass

    def input(self, prompt=""):
        raise AssertionError("input() should not be used by this path")


def test_reset_to_defaults_restores_fresh_state(monkeypatch):
    fake = _ScriptedTerm([5, 7])  # 5 = Reset to Defaults, 7 = Back
    monkeypatch.setattr(barracks, "term", fake)

    state = {
        "hp": 1,
        "str_mod": 200,
        "con_mod": -200,
        "dex_mod": 50,
        "elemental_res": {"fire": 2.0, "water": 0.5},
    }

    result = barracks._dummy_config_menu(state)

    assert result == "back"
    assert state["hp"] == DEFAULT_DUMMY_CONFIG["hp"]
    assert state["str_mod"] == DEFAULT_DUMMY_CONFIG["str_mod"]
    assert state["con_mod"] == DEFAULT_DUMMY_CONFIG["con_mod"]
    assert state["dex_mod"] == DEFAULT_DUMMY_CONFIG["dex_mod"]
    assert state["elemental_res"] == DEFAULT_DUMMY_CONFIG["elemental_res"]
    # The reset must not hand back the module default's nested dict.
    assert state["elemental_res"] is not DEFAULT_DUMMY_CONFIG["elemental_res"]
    assert fake.pause_count == 1
    assert "Dummy reset to defaults." in fake.messages


def test_reset_does_not_pollute_module_defaults(monkeypatch):
    fake = _ScriptedTerm([5, 7])
    monkeypatch.setattr(barracks, "term", fake)

    state = copy_default_dummy_config()
    state["elemental_res"]["fire"] = 5.0  # simulate a resistance edit

    assert barracks._dummy_config_menu(state) == "back"
    assert state["elemental_res"]["fire"] == 1.0
    assert DEFAULT_DUMMY_CONFIG["elemental_res"]["fire"] == 1.0


def test_copy_default_dummy_config_has_independent_resistances():
    first = copy_default_dummy_config()
    second = copy_default_dummy_config()

    first["elemental_res"]["fire"] = 3.0

    assert second["elemental_res"]["fire"] == 1.0
    assert DEFAULT_DUMMY_CONFIG["elemental_res"]["fire"] == 1.0
