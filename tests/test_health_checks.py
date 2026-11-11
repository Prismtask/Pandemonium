import importlib
import os

import pytest

from pandemonium.combat.stats import player_str_mod
import pandemonium.core.save_load as save_load


def test_player_mod_helpers_use_effective_values():
    player = {
        "attributes": {"Strength": 5},
        "active_buffs": [{"type": "blessing", "stat": "Strength", "value": 3}],
    }

    assert player_str_mod(player) == 8


def test_save_directory_uses_project_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    reloaded = importlib.reload(save_load)

    filename = reloaded.get_filename(7)
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(reloaded.__file__)))
    )
    expected_dir = os.path.join(project_root, "savefile")

    assert os.path.dirname(filename) == expected_dir
