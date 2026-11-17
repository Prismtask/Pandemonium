"""
gui/widgets/acquire_dialog.py — GUI dialog for a full inventory.

Shown when a drop cannot be added to the bag. The player either discards an
existing item (the new drop is acquired) or drops the new item. Used by the
DungeonScreen facility thread and by CombatScreen loot prompts so neither
falls back to a console input() prompt.
"""

import tkinter as tk

from pandemonium.gui.theme import Theme
from pandemonium.resources.items import is_unique_item

# ── Standard dialog size ──────────────────────────────────────────────────
# Fixed so the window never jumps around between drops. The width covers the
# longest possible line at the default font: a 32-char name (e.g. "Legendary
# Inferno Battle Harness") + slot tag (accessory) + the longest stat line (60
# chars, Certain Someone Black Gloves) + rarity, with room for padding,
# scrollbar, and borders. 440px fits the 12-row listbox plus header/buttons.
DIALOG_WIDTH = 1062
DIALOG_HEIGHT = 440


def show_acquire_dialog(parent, screen_manager, player, item, log_fn=None):
    """Show the inventory-full dialog and block until the player chooses.

    Args:
        parent: widget used to find the toplevel when no screen_manager exists.
        screen_manager: ScreenManager (provides the root window).
        player: player dict.
        item: the incoming item dict.
        log_fn: optional callable(text) used to echo the result to the
                caller's log / output panel.

    Returns:
        True if the incoming item ended up in the inventory, False if dropped.
    """
    from pandemonium.inventory.core import (get_inventory_caps, count_inventory,
                               get_sorted_equipment, get_sorted_items,
                               remove_item_by_reference)
    from pandemonium.inventory.legacy_ui import _format_equipment_stat_line

    def _log(text):
        if log_fn is not None:
            try:
                log_fn(text)
            except Exception:
                pass

    is_equip = item.get("type") == "equipment"
    cat_name = "Equipment" if is_equip else "Items"
    equip_cap, other_cap = get_inventory_caps(player)
    equip_count, other_count = count_inventory(player)
    cur_count = equip_count if is_equip else other_count
    cur_cap = equip_cap if is_equip else other_cap

    candidates = get_sorted_equipment(player) if is_equip else get_sorted_items(player)
    # Filter out unique items — they cannot be discarded
    candidates = [itm for itm in candidates if not is_unique_item(itm)]

    result = [False]  # True = acquired, False = dropped

    # ── Build the text up front so all rows share aligned columns ──────
    header_text = (f"⚠️  Your {cat_name.lower()} bag is full! "
                   f"({cur_count}/{cur_cap})")
    rarity = item.get("rarity", "common")
    rarity_color = Theme.RARITY_COLORS.get(rarity, Theme.TEXT)

    item_text = f"New drop: {item['name']}"
    if is_equip:
        item_text += f"  {_format_equipment_stat_line(item)}"
    item_text += f"  [{rarity}]"

    hint_text = "Choose an item to discard, or drop the new item:"

    rows = []
    for itm in candidates:
        count_str = (f" (x{itm.get('count', 1)})"
                     if not is_equip and itm.get('count', 1) > 1 else "")
        rows.append((
            f"{itm['name']}{count_str}",
            f"({itm['slot']})" if is_equip else f"({itm['type']})",
            _format_equipment_stat_line(itm) if is_equip else "",
        ))
    name_w = max((len(r[0]) for r in rows), default=0)
    tag_w = max((len(r[1]) for r in rows), default=0)
    stat_w = max((len(r[2]) for r in rows), default=0)
    row_labels = []
    for idx, (itm, (name_part, tag_part, stat)) in enumerate(zip(candidates, rows)):
        label = f"{idx + 1:>2}. {name_part:<{name_w}}  {tag_part:<{tag_w}}"
        if stat_w:
            label += f"  {stat:<{stat_w}}"
        label += f"  [{itm.get('rarity', 'common')}]"
        row_labels.append(label)

    root = screen_manager.root if screen_manager else parent.winfo_toplevel()

    # Fixed standard size; the clamp only guards tiny screens so the dialog
    # can never open partially off-screen.
    dw = min(DIALOG_WIDTH, root.winfo_screenwidth() - 40)
    dh = DIALOG_HEIGHT

    dialog = tk.Toplevel(root)
    dialog.title("Inventory Full")
    dialog.transient(root)
    dialog.grab_set()
    dialog.resizable(False, False)
    dialog.configure(bg=Theme.BG_DARK)

    # Center
    dialog.update_idletasks()
    px = root.winfo_x()
    py = root.winfo_y()
    pw = root.winfo_width()
    ph = root.winfo_height()
    dialog.geometry(f"{dw}x{dh}+{px + (pw - dw)//2}+{py + (ph - dh)//2}")

    # Header
    tk.Label(
        dialog, text=header_text,
        bg=Theme.BG_DARK, fg=Theme.ACCENT,
        font=Theme.FONT_BOLD,
    ).pack(pady=(12, 4))

    # New item info
    tk.Label(
        dialog, text=item_text,
        bg=Theme.BG_DARK, fg=rarity_color,
        font=Theme.FONT,
    ).pack(pady=(0, 8))

    tk.Label(
        dialog, text=hint_text,
        bg=Theme.BG_DARK, fg=Theme.TEXT_DIM,
        font=Theme.FONT_SMALL,
    ).pack(pady=(0, 4))

    # Candidate list with scrollbar
    list_frame = tk.Frame(dialog, bg=Theme.BG_DARK)
    list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

    scrollbar = tk.Scrollbar(list_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    cand_list = tk.Listbox(
        list_frame,
        yscrollcommand=scrollbar.set,
        bg=Theme.BG_MID,
        fg=Theme.TEXT,
        font=Theme.FONT,
        selectbackground=Theme.ACCENT,
        selectforeground=Theme.BG_DARK,
        height=min(12, max(1, len(candidates))),
        exportselection=False,
    )
    cand_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=cand_list.yview)

    for label in row_labels:
        cand_list.insert(tk.END, label)

    # Buttons — both anchored to the bottom right.
    btn_frame = tk.Frame(dialog, bg=Theme.BG_DARK)
    btn_frame.pack(fill=tk.X, padx=12, pady=(4, 12))

    def _discard_selected():
        sel = cand_list.curselection()
        if sel:
            idx = sel[0]
            if 0 <= idx < len(candidates):
                discarded = candidates[idx]
                remove_item_by_reference(player, discarded)
                player.setdefault("inventory", []).append(item)
                _log(f"Discarded {discarded['name']}. Acquired {item['name']}!")
                result[0] = True
        dialog.destroy()

    def _drop_new():
        _log(f"You drop the {item['name']}.")
        result[0] = False
        dialog.destroy()

    # Packed first so it sits at the far right; the Discard button then
    # lands to its left, keeping the original left/right order.
    tk.Button(
        btn_frame, text="Drop Item",
        command=_drop_new,
        bg="#5a3a5a", fg=Theme.BUTTON_FG,
        font=Theme.FONT_BOLD, width=12,
    ).pack(side=tk.RIGHT)

    discard_btn = tk.Button(
        btn_frame, text="Discard",
        command=_discard_selected,
        state=tk.DISABLED,
        bg=Theme.ACCENT, fg=Theme.TEXT_HEADER,
        disabledforeground=Theme.TEXT_DIM,
        font=Theme.FONT_BOLD, width=12,
    )
    discard_btn.pack(side=tk.RIGHT, padx=(0, 6))

    # Discard stays disabled until an item is actually selected.
    def _on_list_select(_event=None):
        discard_btn.config(
            state=tk.NORMAL if cand_list.curselection() else tk.DISABLED
        )

    cand_list.bind("<<ListboxSelect>>", _on_list_select)

    # Double-click to discard
    cand_list.bind("<Double-Button-1>", lambda e: _discard_selected())

    dialog.protocol("WM_DELETE_WINDOW", _drop_new)
    dialog.wait_window()

    return result[0]
