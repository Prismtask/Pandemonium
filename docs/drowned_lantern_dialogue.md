# The Drowned Lantern — Dialogue & Interaction Script

Status: **proposal / for review** — no code yet.
Companion docs: `lantern_isle_design.md` (mechanics/quests) · `quest_system_design.md`
(quest runtime) · `modding_design.md` (delivery).

This is the scene-by-scene dialogue and interaction spec. It is written to be
implementable with the existing `term.menu` / `choice_dialog` / `StoryScreen` patterns.

**Format**

- `▸` entry narration.
- `1)` a menu option; `↳` the response.
- `[flag]` sets a story flag; `[quest]` advances an objective.
- `KEEPER:` / `DAUGHTER:` are spoken lines. **`DAUGHTER` is Marian** — the companion's
  locked name. The label stays `DAUGHTER` because it is her role before the reveal; she
  says the name in 18b and the Sanctum door (18e). Code id: `lantern_marian`.
- **Loop variants** are authored per scene; the same room is never identical on a
  wrong-loop repeat.

**Act 2 rule (the spine of this script):** the festival quest is always available and
always completable. Completing it in full repeats Act 2 with **no progress**. Giving
**one harbor-lamp part** and stopping triggers a **correct loop** that keeps the part.
The dialogue must teach that distinction without a tutorial box.

**Lore primer (deliver through dialogue, not exposition dumps):**

- **The whole island died in the Ninth Tide.** When the Accord broke, the other eight
  lights went dark; the Sleeper stirred; the sea rose. The town drowned in one night.
  The Keeper survived inside the lighthouse. His wife and daughter were on the *Saltwake*,
  which broke on the reef.
- **The Sleeper was already the dreamer.** It is not a god and not a Bound Power. It dreams
  the deep. The Nine Lights were built to keep it dreaming. The Ninth Light is a lens, not
  a creator.
- **The dream is the whole town, not just the Keeper's family.** The Keeper turned the lens
  on the drowned town; the Sleeper dreamt it back — every street, every neighbour, every
  festival banner. He feeds it ships and memories to keep it bright.
- **The festival is the last day before the wave.** The town is always preparing for a
  festival that will happen tomorrow because the wave is always tomorrow.
- **Marian is lucid because she was the last lost** and the dream holds her tightest.
  The wife is a memory-echo like the rest of the town. The Keeper never says her name out
  loud — that is how the script shows the grief before the reveal.
- **The Keeper is the human antagonist, not the Sleeper.** He is the hand on the lens. The
  Sleeper is the engine.

---

# Act 1 — The First Day

## 1. The Black-Sailed Ferry (Q0)

▸ The dock at night. A black-sailed ferry waits at the end of the pier. No crew. No
lantern. The plank is already down.

**Ferryman**
> "Passage to the last light. No crew. No freight. No questions."
> "You'll want to leave your companions ashore. The light takes one."
> "Your cargo stays at the dock. Your ship stays moored. You'll understand when you
> see the water."

**(Level gate — under 40)**
> "Not you. Not yet. The light does not take the green. Come back when the sea knows
> your name — forty winters, at least. Sixty, and you'll still be lucky."
↳ The ferry does not move. No flag is set; the quest never appears in the Journal.

**Menu**
1) "What is the last light?" ↳ "A lighthouse. The only one still burning. It has been
   burning a long time." `[flag: heard_last_light]`
2) "Why alone?" ↳ "Because the light is looking for one. More than one and it looks
   away. One, and it calls." `[flag: heard_lure_rule]`
3) "Who are you?" ↳ "A ferryman. I take people to the island. I do not bring them back."
   `[flag: met_ferryman]`
4) "I'm ready." ↳ The plank creaks. The ferry pushes off.

**Before boarding**
> "One warning. The island is not what it looks like. The town is not what it looks
> like. If you want to come back, find the light and finish what the Keeper started.
> Until then, the sea will not take you."

`[flag: lantern_journey_started]` → bench allies, stow cargo, lock the pack.

**Crash**
▸ The crossing is quiet for an hour. Then the water goes still. The ferry shudders,
once, like something underneath has taken hold of the keel. The black sail tears. The
lighthouse beam sweeps over the water — not a warning, a hand closing.
> "Don't fight it," the ferryman says. He does not sound afraid. "It only hurts if you
> fight."
▸ The ferry breaks on the reef. Cold water. Then nothing.

---

## 2. The Beach (Q1)

▸ You wake on a beach the colour of old paper. The wreck is behind you, broken in three
pieces. The lighthouse is ahead, dark. Between them: a town. Smoke from chimneys. Nets
drying. A festival banner moving in a wind you cannot feel.

**Menu**
1) "Search the wreck." ↳ A brass key on a nail in the captain's cabin. It is warm.
   `[flag: lamp_key]` `[quest: salvage the key]`
2) "Call out." ↳ The gulls answer. The town does not.
3) "Walk toward the town." ↳ The sand under your boots is dry. The tide does not follow
   you.

**Narration**
> The air tastes of salt and lamp oil. Somewhere ahead, a bell rings once — the sound a
> town makes when it is pretending not to be waiting.

---

## 3. The Harbor & the Dock (Q1)

▸ The harbor looks alive. Boats bob at their moorings. A woman mends a net. A man rolls
a barrel. A child runs past with a paper fish on a string. No one looks at the lighthouse.

**The Dock**
▸ A girl sits at the end of the dock, her feet in the water. She does not turn.

**Menu**
1) "Call to her." ↳ She does not move. `[flag: dock_girl_seen]`
2) "Touch her shoulder." ↳ Your hand passes through the air above her shoulder. The
   tide moves through her ankles. She does not blink. `[flag: dock_girl_seen]`
   `[flag: dock_clue_touched]`
3) "Sit beside her." ↳ You sit. She does not speak. After a while you notice the gulls
   do not land near her. `[flag: dock_girl_seen]` `[flag: dock_clue_sat]`

**Narration (any option)**
> She is the only thing in the harbor that is not moving. You do not know why that is
> worse than the dead fish on the pier.

`[quest: meet the town]` → the lighthouse door.

---

## 4. The Lighthouse Door — Keeper's First Meeting (Q1)

▸ The lighthouse door is open. A man waits in the doorway. He is tall, grey, and tired
in a way that looks permanent. He smiles like he has been practising.

**KEEPER**
> "You're the one the sea sent. Welcome. We don't get many."
> "I'm the Keeper. This is the Ninth Light. The last one. You're lucky — the festival is
> tomorrow."
> "The lamp must burn before the festival. It always has. I'd do it myself, but the
> light doesn't answer me anymore."
> "Ask the neighbours where the parts are. They remember. They're good at remembering."

**Menu**
1) "What is this place?" ↳ "A town. A harbour. A festival. The same as every year."
   `KEEPER:` "Isn't it enough?"
2) "What is the lighthouse?" ↳ `KEEPER:` "The Ninth. There were others, once. They went
   dark. This one kept its promise." `[flag: heard_ninth_light]`
3) "Why can't you leave?" ↳ `KEEPER:` "Someone has to keep the light." He does not meet
   your eyes. `[flag: keeper_cannot_leave]`
4) "Who is the girl on the dock?" ↳ `KEEPER:` "My daughter." A pause. "She likes the
   water." `[flag: clue_daughter]`
5) "I'll help." ↳ `KEEPER:` "I knew you would." `[quest: festival offered]` `[flag:
   festival_offered]`

**Leaving**
> "Ask the neighbours. Oil, wick, flame. They'll tell you where. They always do."
> "And don't worry about the lamp. The light knows what it's doing."

`[quest: Q1a Residential Clue]`

---

## 5. Residential — The Clue (Q1a)

▸ The residential lane is narrow and warm. Wash lines. A cat asleep on a wall. Three
children playing a game with a paper fish. A bread seller at a stall. An old woman in a
window, watching.

**Entry menu**
1) "Ask the children." → 5a
2) "Ask the bread seller." → 5b
3) "Ask the old woman." → 5c
4) "Ask about the lighthouse." → 5d
5) "Leave." → "They wave. The children do not stop playing."

### 5a — The children

▸ The children are playing a game with a paper fish. The fish goes round and round. They
never get tired.

**Menu**
1) "What are you playing?" ↳ "The festival! The fish goes to the lamp, and the lamp eats
   it, and then we play again." `[flag: clue_festival_game]`
2) "Where are the lamp parts?" ↳ They sing:
   > "Oil where the boats sleep,
   > wick where the bread is sold,
   > flame where the light was old."
   `[flag: clue_parts]` `[quest: clues — parts]`
3) "Who is the girl on the dock?" ↳ "The Keeper's girl. She doesn't play anymore."
   `[flag: clue_daughter]`

**KEEPER (from the lane)**
> "Don't tire them out. They have a festival tomorrow."
> He is already walking away.

### 5b — The bread seller

▸ The bread is warm. It has no smell.

**Menu**
1) "Where are the lamp parts?" ↳ "Same as every year. Oil from the harbour, wick from the
   chandler, flame from the temple. You'll want to take them one at a time." `[flag:
   clue_parts]` `[flag: clue_one_at_a_time]` `[quest: clues — parts]`
2) "One at a time?" ↳ "The lamp's greedy. Give it everything and it thinks the day's
   over. Give it a little and it waits." She smiles. "Like a cat." `[flag:
   clue_correct_loop]`
3) "What is the lighthouse?" ↳ "The Ninth. My grandmother said the others went dark
   because no one remembered to feed them." `[flag: clue_lighthouse]`
4) "What is the Keeper like?" ↳ "He buys a loaf every morning. Same loaf. Same coin. I
   don't ask where he puts it." `[flag: clue_keeper_loaf]`

**KEEPER (passing)**
> "Bread for the festival. Put it on my tab."
> The bread seller does not look at him. "You don't have a tab, Keeper."

### 5c — The old woman

▸ She sits at the window with a cup of tea that is not steaming.

**Menu**
1) "What is the lighthouse?" ↳ "The Ninth. The last. The others are dark, and the sea
   remembers them." `[flag: clue_lighthouse]` `[flag: heard_ninth_light]`
2) "What happened to the town?" ↳ "The town is here. The town is always here." She
   looks at you for the first time. "You're not, are you?" `[flag: clue_not_from_here]`
3) "Who is the Keeper's girl?" ↳ "She sits on the dock. She used to run with the other
   children. Now she watches the water." `[flag: clue_daughter]`
4) "How do I leave?" ↳ "You don't. Not until the light is finished." `[flag:
   clue_cannot_leave]`

### 5d — The lighthouse

▸ You ask the lane about the lighthouse. The answers overlap.

> "The Keeper never leaves it."
> "Not since the wreck."
> "The light is the Ninth."
> "The light is the only one that stayed."
> "The light is a lullaby."

`[flag: clue_lighthouse]` `[flag: clue_lullaby]`

**KEEPER (when you leave the lane)**
> "You've been asking about the light. Good. Ask all you like. It won't answer."
> He is smiling. It does not reach his eyes.

`[quest: returning to the Keeper]` → Q1b.

---

## 6. Market — The Wick (Q1b)

▸ The market is bright and loud and slightly wrong. The same stall shouts the same
price. The same fish turns on the same hook. The chandler's shop smells of wax and old
smoke.

**Chandler**
> "Wick for the festival? You can have it. But first — the granary's full of them.
> Rats with too many eyes. **Please help me get rid of these monsters first, and I'll
> give you the item.**"

**Menu**
1) "I'll help." → **Combat — The Market Granary**; after victory the chandler hands over
   the wick. `[quest: wick]` `[flag: has_wick]` `[flag: market_granary_cleared]`
2) "What are they?" ↳ "They came up from the water. They always come up from the water.
   The light keeps the big things asleep, not the small ones." `[flag: clue_market_rats]`
3) "Not now." ↳ "Then no wick. The granary can wait. The festival can't."
4) "Ask about the lighthouse." ↳ "The Ninth? My grandfather sold candles to the Keeper
   before the wave. He says the light used to be a warning. Now it's a welcome."
   `[flag: clue_light_changed]`
5) "Ask about the Keeper." ↳ "He's been keeping that light since before the wave. Longer
   than I've been alive. Longer than the road." `[flag: clue_keeper_age]`

**Combat — The Market Granary**
▸ The granary door opens on a dark full of small eyes. 2–3 cave rats / shadow rats. The
player is solo in Act 1. On victory:
> The chandler opens the door, holds her nose, and hands you the wick. It is dry and warm.
> "There. Take it. Same as last year. Same as every year."

**KEEPER (at the market edge)**
> "You have the wick. Good. The oil is at the harbour. The flame is at the temple."
> "Don't light it early. The festival has a schedule."

---

## 7. Temple — The Flame (Q1b)

▸ The temple is small and white and open to the sky. A priest tends a flame in a brass
bowl. The choir is three old women humming a song that has no words.

**Priest**
> "The flame remembers everyone. That's the trouble with flames."
> "Take it to the lamp. It knows the way home."

**Menu**
1) "What is this flame?" ↳ "The Ninth Light's daughter-flame. Every year we give it
   back. Every year it comes home." `[flag: clue_flame]`
2) "What is the lighthouse?" ↳ "A lens. The Nine Lights were built to keep the Sleeper
   dreaming. The other eight went dark. The Ninth kept its promise." `[flag:
   clue_sleeper]`
3) "What happened to the town?" ↳ "The Ninth Tide. The night the lullaby faltered. The
   sea rose. The town drowned. The light kept the morning." `[flag: clue_ninth_tide]`
4) "Who is the Keeper's wife?" ↳ The priest looks at the memorial wall. A name is
   carved there. The letters are worn smooth. "He comes every morning. He never reads
   it." `[flag: clue_wife]`
5) "Take the flame." ↳ `[quest: flame]` `[flag: has_flame]`

**KEEPER (at the temple door)**
> "The choir used to be louder. Before the wreck."
> He does not come inside.

---

## 8. The Festival Lamp (Q1b — the wrong loop)

▸ The harbour lamp stands at the end of the pier. Oil, wick, flame. The town gathers.
The Keeper stands beside the lamp. The girl on the dock has turned her head. She is
watching you.

**KEEPER**
> "Go on. Light it. The town has waited long enough."
> "You'll feel better. We always do."

**Menu**
1) "Light the lamp." ↳ The flame takes. The town cheers. The Keeper exhales.
   `[flag: festival_lit]`
2) "Wait." ↳ `KEEPER:` "There's nothing to wait for. The day is almost over."
   → back to the menu.

**After lighting**
▸ The flame is very bright. The cheering goes on a little too long. Then the faces
around you go smooth, like paper. The Keeper's smile stays exactly where it is.

**KEEPER**
> "There. The day is done."
> "Don't worry. We'll do it again tomorrow."

▸ The light fills everything. You wake on the beach. The wreck is behind you. The
lighthouse is ahead. The town is between them, and the festival is tomorrow.

**Narration**
> The sand is dry. The tide does not follow you. The girl on the dock has not moved.
> Somewhere behind your eyes, a bell rings once.

`[quest: Q1b complete — FAILED, the day began again]` → Act 2.

---

# Act 2 — The Second Day

## 9. The Dock, Loop 2 — "You noticed?" (Q2)

▸ Same beach. Same wreck. Same smoke. The town is exactly as it was. The girl on the
dock is not.

▸ She is looking at you. Her feet are in the water. The tide goes through them.

**DAUGHTER**
> "You noticed."
> "The tide. The gulls. The bread. The way the town says the same thing twice."
> "I've been waiting for someone who noticed."

**Menu**
1) "Noticed what?" ↳ "That none of this is happening. Not anymore." `[flag:
   daughter_truth]`
2) "You're the Keeper's daughter." ↳ "I was. I still am. That's the problem." `[flag:
   daughter_truth]`
3) "Who are you?" ↳ "Someone who stayed. Everyone else is a memory. I'm the part that
   knows." `[flag: daughter_truth]`
4) "What is this place?" ↳ "A day that won't end. My father's day. He keeps it warm."
   `[flag: daughter_truth]` `[flag: clue_father]`

**DAUGHTER (joining)**
> "I can help you. I can walk where the memory is thin. But I can't leave. Not yet."
> "Names are for people who get to leave. Call me what I am."
`[flag: daughter_joined]` `[quest: Q2 complete]`

**KEEPER (watching from the lighthouse road)**
> "You've met my daughter. She likes the water."
> He does not come closer. The road behind him is the same road as yesterday.

---

## 10. The Keeper, Act 2 — the trap (Q2)

▸ The Keeper waits at the lighthouse door. He is holding a list. It is the same list.

**KEEPER**
> "You're back. Good. The lamp needs oil, wick, and flame. The festival is tomorrow."
> "It's always tomorrow."

**Menu**
1) "We did this already." ↳ `KEEPER:` "Did we? I don't remember. The light does the
   remembering." `[flag: keeper_denial]`
2) "What happens if I light the lamp again?" ↳ `KEEPER:` "The day ends. The town is
   happy. We begin again." `[flag: keeper_loop_explained]`
3) "Why are you doing this?" ↳ `KEEPER:` "Because the alternative is a morning without
   them." `[flag: keeper_grief]`
4) "I'm not lighting it." ↳ `KEEPER:` "Then the festival will wait. It's very good at
   waiting." `[flag: refuse_festival]`

**DAUGHTER (if present)**
> "He knows. He just can't say it while the light is listening."

**Quest board**
> The festival quest remains on the Journal. It is always completable. Completing it
> will repeat the day with no progress. The Daughter's line is the hint.

`[quest: find another way]`

---

## 10a. The Festival Lamp, Act 2 — the wrong loop (repeatable)

▸ The Keeper is at the lamp. The town is gathered. The Daughter is not. The lamp is
already lit — or it is waiting to be lit. It is always waiting.

**If the player completes the festival quest in Act 2:**
▸ The flame takes. The town cheers. The Keeper exhales. The light fills everything. You
wake on the beach. Nothing has changed except the number behind your eyes.

**KEEPER (wrong loop 1)**
> "Back so soon? The lamp is still waiting. It's always waiting."
> "You look tired. The festival does that."

**KEEPER (wrong loop 2)**
> "You keep doing the same thing. So do I."
> "The bread is warm. The girl is on the dock. The day is tomorrow. Isn't that enough?"

**KEEPER (wrong loop 3)**
> "Don't listen to her. She's not real."
> "She's the one thing in this town that doesn't belong. You see that, don't you?"

**DAUGHTER (wrong loop 3, blocking the lamp)**
> "Stop. You're not helping them. You're helping him."
> "One part. That's all it takes. Give the lamp one part and walk away. The loop will
> keep it. The loop will let you through."
> "If the market is gone, I'll remember the wick for you. I remember all of it."
> "If you light it again, I won't be on the dock when you wake up."

**Residents (wrong loop 3)**
> The bread seller closes the stall. The children stop playing. The old woman closes the
> window. The town is still there, but it has stopped pretending.

`[wrong_loops += 1]` `[no progress]` → Act 2 start; at 3 wrong loops, the festival route
is blocked and the correct-loop hint is forced.

---

## 11. Market, Act 2 — the hint (Q3)

▸ The market is the same. The bread seller is selling the same bread. The fishmonger is
turning the same fish. The residential lane is gone — where it should be, there is only
salt grass and a child's paper fish nailed to a post.

**Menu**
1) "Ask the bread seller." ↳ "Back again? The lamp's greedy, dear. Give it one thing and
   it waits. Give it everything and it starts the day over." `[flag:
   clue_correct_loop]` `[quest: clues — one at a time]`
2) "Ask the fishmonger." ↳ "The lane? There's no lane. There's never been a lane." The
   Daughter looks at the paper fish. "There was. I remember it." `[flag:
   clue_lane_gone]`
3) "Ask about the Keeper." ↳ "He's been up at the light since the wreck. He doesn't
   sleep. He doesn't eat. He just keeps the morning." `[flag: clue_keeper_grief]`
4) "Ask about the rhyme." ↳ The bread seller sings it, softer:
   > "Oil where the boats sleep,
   > wick where the bread is sold,
   > flame where the light was old —
   > **one for the road, one for the day, one for the light to stay.**"
   `[flag: clue_correct_loop]` `[quest: clues — one at a time]`

**DAUGHTER**
> "One part. Then stop. The loop keeps what you learn. That's the only way through."
> "The children are still here. They're just not in the lane anymore."

**KEEPER (from the market edge)**
> "Don't fill their heads with that. The lamp needs all three."
> The bread seller looks at him. "You keep saying that, Keeper."

---

## 12. Harbor — Oil (Q3, correct loop)

▸ The oil house smells of tar and old engines. Barrels line the wall. The oil is black
and slow. A gull watches from the rafters.

**Menu**
1) "Take the oil." ↳ `[quest: oil]` `[flag: has_oil]`
2) "Ask the oilman about the lamp." ↳ "The lamp drinks it. Every year it drinks more.
   Since the wave, it drinks and drinks." `[flag: clue_lamp_drinks]` `[flag:
   clue_ninth_tide]`
3) "Ask about the wreck." ↳ "The ferry? Your ferry? It's on the reef. It's been on the
   reef since before you got here." `[flag: clue_wreck_old]`

**KEEPER (at the door)**
> "You have the oil. The wick is at the market. The flame is at the temple."
> "Bring them all. Light the lamp. End the day."

**Correct loop — take the oil and stop**
▸ You put the oil in your pack and walk away from the lamp. The Keeper watches you. The
town goes quiet. The light flickers, once, like a held breath.

**DAUGHTER**
> "That's it. One part. The loop keeps what you learn."
> "The day will start again. You'll remember. That's the difference."

▸ The light fills everything. You wake on the beach. The oil is still in your pack. The
town is the same. The Daughter is waiting on the dock.

`[flag: correct_loop_oil]` `[quest: oil kept]`

---

## 13. Market — Wick (Q3, correct loop)

▸ The chandler's shop is the same. The wick is the same. The chandler's smile is the
same. The granary door is shaking.

**Chandler**
> "Back for the wick? Same as last year. But the granary's full again. They're back.
> They're always back. **Help me again and the wick is yours.**"

**Menu**
1) "I'll help." → **Combat — The Market Granary (echo)**; after victory the chandler
   hands over the wick. `[quest: wick]` `[flag: has_wick]`
2) "What are they now?" ↳ "Memory. The dream keeps making them. They don't know they're
   dead. Neither does the bread." `[flag: clue_memory_rats]`
3) "Ask about the loop." ↳ "The lamp's greedy. One thing at a time. My mother told me
   that. Or my grandmother. Someone did." `[flag: clue_correct_loop]`
4) "Ask about the Keeper's daughter." ↳ "She used to run errands for me. Then the wave.
   Now she sits on the dock." `[flag: clue_daughter_wreck]`

**Combat — The Market Granary (echo)**
▸ 2–3 shadow rats (memory-echoes). The Daughter is present. On victory:
> The chandler looks at the empty granary. "Same wick. Same as every year."

**KEEPER (at the market edge)**
> "One part. Always one part. You are cruel."
> He says it without anger. That is worse.

**Correct loop — take the wick and stop**
▸ The wick goes into your pack beside the oil. The light flickers. The town holds its
breath. You wake on the beach. Both parts are still there.

**DAUGHTER**
> "Two. One more. The flame is at the temple. Don't let him make you light it."

`[flag: correct_loop_wick]` `[quest: wick kept]`

---

## 14. Temple — Flame (Q3, correct loop)

▸ The temple is the same. The flame is the same. The choir is the same three old women,
humming the same song. The priest looks older than yesterday. So does the flame.

**Priest**
> "You're back. The flame remembers you."
> "It remembers everyone. That's the trouble."
> "The Sleeper was here before the town. The light is a lullaby. When the lullaby
> faltered, the sea rose."

**Menu**
1) "Ask about the loop." ↳ "The lamp is a mouth. Give it a bite and it waits. Give it a
   meal and it sleeps. The town sleeps with it." `[flag: clue_correct_loop]`
2) "Ask about the town." ↳ "The town is here. The town is always here. It drowned, dear.
   That's why it's so warm." `[flag: clue_ninth_tide]`
3) "Ask about the Keeper's wife." ↳ "She was the light's keeper before him. He took the
   light so he could keep her. That's not the same thing." `[flag: clue_wife_keeper]`
4) "Take the flame." ↳ `[quest: flame]` `[flag: has_flame]`

**KEEPER (at the temple door)**
> "The lamp will not be lit. You know that now."
> He almost looks proud.

**Correct loop — take the flame and stop**
▸ The flame goes into the lantern. Oil, wick, flame. All three. The light flickers, and
this time it does not take you. The town shudders. The Keeper is standing at the temple
door with his hand over his mouth.

**DAUGHTER**
> "Three. That's all of it. Now the wreck. The lens. Then he has to listen."

`[flag: correct_loop_flame]` `[quest: flame kept]` → Q4.

---

## 15. The Wreck (Q4)

▸ The ferry wreck is on the reef, exactly where you left it. Beyond it, further out,
another wreck is caught in the rocks — older, broken-backed, its nameplate gone. The
captain's cabin of your ferry is open. A lantern still burns inside. It has been burning a
long time.

**Drowned Quartermaster**
> "No passage. No freight. No questions."
> The water rises in the cabin. It does not reach the lantern.

**After the fight**
▸ The quartermaster falls apart into salt and old rope. In the safe: the beacon lens,
wrapped in oilcloth. It is warm. It is looking at you.

**[quest: lens]** `[flag: has_lens]`

**KEEPER (on the shore)**
> "You went to the wreck. You shouldn't have."
> "Not yours. The other one. The Saltwake. She's been on this reef since the Ninth Tide."
> "The wave took her. The wave took everything."

**DAUGHTER**
> "He's afraid of what you'll find. He's been afraid of it for a long time."

`[quest: Q4 complete]` → Act 2 epilogue.

---

## 15a. The Lighthouse Interior (Act 2, optional)

▸ The Keeper steps aside. The stairs spiral up. The lamp room is cold. A narrow bed is
made in the corner; no one has slept in it. A child's drawing is pinned to the wall: a
lighthouse, a ship, three stick figures holding hands.

**Menu**
1) "Examine the drawing." ↳ The ship is labelled *Saltwake*. The figures are labelled in
   a child's hand: *Father, Mother, Me.* `[flag: lighthouse_drawing]`
2) "Read the logbook." ↳ It is not a diary. It is a list of ships, dates, and the same
   word: *kept.* The last entry is your ferry. `[flag: lighthouse_log]`
3) "Look at the lamp." ↳ The lamp is dark. It is warm. It is listening. `[flag:
   lighthouse_lamp]`

**KEEPER**
> "Don't touch the logbook. It's not a diary. It's a list."
> "The drawing is hers. She was good at the sea."

`[flag: lighthouse_interior_seen]`

---

## 16. Act 2 Epilogue — the Keeper's confession (Q4a)

▸ The Keeper waits at the lighthouse door. The town is behind him. The festival banners
have stopped moving. The girl on the dock is standing.

**KEEPER**
> "You have the lens. You have the parts. You have her."
> "I suppose you want the truth."

**Menu**
1) "Tell me." ↳ He does.
2) "I already know." ↳ "Then you know why I can't let you finish."
3) "Why did you do it?" ↳ "Because the morning was the only thing I had left."

**The confession**
> "There was a wave. Before yours. The Ninth Tide. The other lights went dark, and the
> sea rose."
> "The town drowned. All of it. The streets. The boats. The festival. Everyone."
> "I was in the light. I survived because I was in the light."
> "My wife and daughter were on the Saltwake. It broke on the reef. I saw it."
> "The light was already a lullaby. The Sleeper was already dreaming. I only turned the
> lens."
> "I asked it to keep them. It kept the town. All of it. Not just them. Everyone."
> "The town came back. The bread came back. The festival came back. She came back."
> "She came back wrong. She knows. She's the only one who knows."
> "I feed it ships. New memories. The dream needs them. The sea brings them. I keep the
> light. It keeps the town."
> "I kept the light burning so she wouldn't have to be alone. I kept it burning so I
> wouldn't have to be alone. I don't know which one was the lie."

**DAUGHTER**
> "I know, Father. I've always known."
> "You didn't save me. You saved the day. That's not the same thing."

**KEEPER**
> "Then why are you helping them?"
> "Because they're still here. Because you're still here."
> "And because the light is tired. I can hear it. It wants to sleep."

**The Warden appears**
▸ The lighthouse beam bends. The town's voices rise together — every voice at once,
saying the same thing:

> "The day is not finished."

▸ The light gathers into a shape. A tall, salt-white figure with the town's faces pressed
under its skin. It speaks with the Keeper's voice, and his wife's, and his daughter's,
and every voice in the square.

**DREAM-WARDEN**
> "The day is not finished."
> "The lamp must burn."
> "The morning must stay."

**KEEPER**
> "I can't stop it. I never could."
> "If you're going to end this, end it."

`[quest: Q4a — defeat the Dream-Warden]`

---

## 17. The Dream-Warden (Q4a boss)

**Intro**
> "You are the one who noticed."
> "The day was warm. The bread was warm. The girl was warm."
> "Why are you cold?"

**Phase lines**
- 50% HP: "The town is still here. The town is still here. The town is still—"
- 25% HP: The Warden's faces turn to the Daughter. `DAUGHTER:` "I'm sorry. I'm not
  staying."
- Defeat: The Warden comes apart into salt, paper, and lamp oil. The beam goes out.

**After the fight**
▸ The lighthouse is dark. The town is silent. The Keeper is on his knees. The Daughter
is already fading.

**DAUGHTER**
> "The reset is coming. The real one. The one the truth can break."
> "Find the anchor. In the drowned place. I'll find you."
> "Don't let him keep the morning."

**KEEPER**
> "Don't go. Please. The day will start again. We can do it better."
> "We can do it better this time."

▸ The dark takes the town. You wake in a place that is not the beach. The sky is the
colour of a closed eye. The lighthouse is a ruin. The town is a ruin. The sea is very
still.

`[quest: Q4a complete]` → Act 3.

---

# Act 3 — The Truth

Act 3 is the full truth act: four ruined districts, four truth keys, a three-wing Sanctum,
three lamps, and the Anchor Warden. The player is solo throughout. Marian is absent;
her voice returns at the anchor.

## 18. Truth Arrival (Q5)

▸ The truth map is the same town, and it is not. The roofs are open. The market is salt
and bone. The temple has no roof. The harbour lamp is a black iron hand. The lighthouse
is the only thing still standing, and it is dark. Beyond the reef, the water is not
water: it is a slow grey shape, breathing.

**Narration**
> Marian is not here. The Keeper is not here. The town is not here. Something is.

**KEEPER (echo)**
> "I only wanted the morning to last."
> "Is that so wrong?"

**Menu (free order)**
1) "The Harbor." → 18a
2) "The Market." → 18b
3) "The Residential lane." → 18c
4) "The Temple." → 18d
5) "The Lighthouse." → locked until all four keys. "The door has four locks. The town has
   four memories. Bring them all."
6) "What is the Sleeper?" ↳ "The shape under the water. The dreamer. It was here before
   the light. The light only gave it a shape." `[flag: sleeper_heard]`

`[quest: Q5 — find the four truth keys]`

---

## 18a. Harbor Truth — The Keeper's Log

▸ The harbour is wreckage. Masts like broken fingers. A drowned clerk sits at a desk
that is half in the water, writing in a ledger that never fills.

**KEEPER (echo)**
> "I wrote every name. I thought keeping the list would make it a ledger, not a crime."

**Menu**
1) "Ask what he is writing." ↳ "The names. The Keeper asks for the names. Every ship.
   Every morning."
2) "Read the ledger." ↳ Ships, dates, the same word: *kept.* The last entry is your
   ferry. `[flag: truth_log_read]`
3) "Take the log." ↳ The clerk does not stop you. The pages are warm.
   `[quest: truth key — log]` `[flag: truth_key_log]`

**Encounter — The Drowned Wharf**
▸ Two drowned echoes rise from the water (shadow rats / drowned sailors). Solo.
After:
> The clerk is gone. The desk is empty. The ledger is in your hands.

**Memory (Keeper's voice)**
> "The Ninth Tide took the harbour first. The boats. The nets. Everyone."
> "The Saltwake was the last. My wife was on her. My daughter was on her."
> "I was in the light. I watched the harbour go under. I did not look away."

**KEEPER (echo)**
> "I kept the list so someone would remember. I didn't think it would be me."

`[flag: truth_harbor_done]`

---

## 18b. Market Truth — Marian's Ribbon

▸ The market is bone stalls and wind. A hollow merchant stands behind a stall of empty
crates, smiling at nothing.

**KEEPER (echo)**
> "She wore it to the festival. The festival never came."

**Menu**
1) "Ask what he is selling." ↳ "Same as always. Same as every year. Nothing. Nothing is
   always in stock."
2) "Search the stall." ↳ A child's ribbon, blue, stiff with salt. A name is stitched into
   the hem in a child's hand: **MARIAN**. `[flag: truth_ribbon_found]` `[flag:
   marian_named]`
3) "Take the ribbon." ↳ The merchant does not blink. `[quest: truth key — ribbon]`
   `[flag: truth_key_ribbon]`

**Encounter — The Empty Stall**
▸ Two hollow echoes. Solo. After:
> The stall collapses into salt. The ribbon is still in your hand.

**Memory (Keeper's voice)**
> "It was her birthday. The day before the wave. She wanted a fish-shaped loaf."
> "The baker made one. She carried it to the dock and fed it to the gulls."
> "I told her the gulls would remember her. I was right. They do."
> "The festival was tomorrow. The wave was tomorrow. No one knew."

**KEEPER (echo)**
> "She would have hated this. That's how I know it's wrong."

`[flag: truth_market_done]`

---

## 18c. Residential Truth — The Wife's Memorial

▸ The lane is roofless. A window stands alone in a wall that is gone. Through it, a
woman weeps without a face.

**KEEPER (echo)**
> "She would have let the town rest. I couldn't."

**Menu**
1) "Ask what she sees." ↳ "The water. It is still in the lane. It never went out."
2) "Look through the window." ↳ A memorial: a name worn smooth, a candle, a child's
   drawing of three stick figures. `[flag: truth_memorial_found]`
3) "Take the memorial candle." ↳ `[quest: truth key — memorial]` `[flag:
   truth_key_memorial]`

**Encounter — The Weeping Window**
▸ Two weeping echoes. Solo. After:
> The window closes. The lane is quiet.

**Memory (Keeper's voice)**
> "She begged me to let them go. I said the light would keep them."
> "She said, 'Then the light is the only one who gets to sleep.'"
> "She was right. I hated her for it. I hated her for leaving me with the light."

**KEEPER (echo)**
> "She would have hated this. That's how I know it's wrong."

`[flag: truth_residential_done]`

---

## 18d. Temple Truth — The Ninth Lamp

▸ The temple is open to a sky with no stars. The choir is three voices with no mouths.
The brass bowl holds a cold flame.

**KEEPER (echo)**
> "The town agreed. I didn't make them. I only asked."

**Menu**
1) "Ask what they are singing." ↳ "The lullaby. The one that keeps the Sleeper asleep.
   The one that keeps us here."
2) "Ask about the town's choice." ↳ "We chose the morning. We chose it together. We did
   not choose the wave."
3) "Take the cold flame." ↳ It burns your hand without heat. `[quest: truth key — flame]`
   `[flag: truth_key_flame]`

**Encounter — The Choir**
▸ Two choir echoes. Solo. After:
> The singing stops. The flame is in your lantern.

**Memory (Keeper's voice / the choir)**
> "The town agreed. That is the part no one says."
> "They knew the morning was a lie. They chose it anyway."
> "The Ninth Tide was the lullaby breaking. The town chose the dream instead."
> "The light sang, and the town slept, and the Sleeper slept under the song."

**KEEPER (echo)**
> "I told myself they wanted to stay. I told myself every morning."

`[flag: truth_temple_done]`

---

## 18e. The Sanctum Door (Q5 complete)

▸ The lighthouse door has four locks. The log, the ribbon, the candle, the cold flame.
They fit. The door opens on a stair that goes down, not up.

**KEEPER (echo)**
> "The Archive. The Choir. The Vault. I kept everything."
> "I never kept the one thing that mattered."

**DAUGHTER (voice)**
> "I'm here. I'm just not all here."
> "Three wings. Three lamps. Then the anchor. Then me."
> "Marian. Say it once, before we go down. My father stopped saying it the day the
> water came."
`[flag: marian_named]`

`[quest: Q5 complete]` → Q5a.

---

## 19. The Drowned Archive (Q5a — wing 1)

▸ The first wing is a library under water. Shelves of ledgers. Names on every spine.
The water is knee-deep and warm.

**Rooms (3–4): The Ship Ledgers / The Name Wall / The Drowned Desk / The Archivist's Office**

**Room beats**
- **The Ship Ledgers:** your ferry is already in the ledger. So is the *Saltwake*.
- **The Name Wall:** every name in the town, carved small. Hers is near the bottom.
- **The Drowned Desk:** the Archivist's ink is still wet. It smells of the sea.
- **The Archivist's Office:** the first lamp, and the thing that has been writing.

**The Archivist**
> "Every name. Every ship. Every morning."
> "The Keeper asked me to keep them. I kept them. I am still keeping them."

**After:** The Archivist dissolves into ink. On the desk: the first lamp.

**First lamp — the Keeper's Log**
▸ You place the log in the lamp. The flame is the colour of a harbour at dawn. The water
recedes. A checkpoint.
`[quest: archive cleared]` `[flag: sanctum_lamp_1]`

**KEEPER (echo)**
> "I kept the list so someone would remember. I didn't think it would be me."

---

## 19a. The Choir (Q5a — wing 2)

▸ The second wing is a chapel with no roof and no floor. The choir stands on the water.
They are singing the lullaby.

**Rooms (3–4): The Hymn Books / The Empty Choir / The Bell / The Cantor's Pulpit**

**Room beats**
- **The Hymn Books:** the lullaby, written in a hundred hands. The last page is blank.
- **The Empty Choir:** the voices are still singing. There is no one in the seats.
- **The Bell:** it rings once when you enter. It has no clapper.
- **The Cantor's Pulpit:** the second lamp, and the mouth that will not stop.

**The Cantor**
> "Sleep. Sleep. The morning is warm."
> "You are the only one who wants to wake up."

**After:** The Cantor's mouth closes. On the pulpit: the second lamp.

**Second lamp — Marian's Ribbon**
▸ The ribbon burns blue. The choir stops. A checkpoint.
`[quest: choir cleared]` `[flag: sanctum_lamp_2]`

**KEEPER (echo)**
> "They wanted to stay. I told myself they wanted to stay."

---

## 19b. The Anchor Vault (Q5a — wing 3)

▸ The third wing is a vault of black iron. Nine lamps line the wall, eight dark, one
cold. In the centre: a ring of iron with a lens of sea-glass. The Anchor.

**Rooms (3–4): The Nine Lamps / The Drowned Stair / The Vault Door / The Anchor Chamber**

**Room beats**
- **The Nine Lamps:** eight dark, one cold. The cold one is still warm.
- **The Drowned Stair:** the water rises with you. It does not touch the lamps.
- **The Vault Door:** the anchor's lock. It opens on the Keeper's voice.
- **The Anchor Chamber:** the third lamp, the fourth key, and the Warden.

**The Anchor Warden**
> "The anchor is not yours."
> "The dream is not yours."
> "Go back to the day. It will be warm."

**Third lamp — the Wife's Memorial**
▸ You place the candle in the third lamp. The flame is the colour of a kitchen at night.
The Warden's salt skin cracks. `[flag: sanctum_lamp_3]`

**The fourth key — the cold flame**
▸ The Ninth Lamp's cold flame goes into the last lamp. The Warden's true shape shows: a
drowned keeper, holding a door shut.

---

## 20. The Anchor Warden (Q5b — final boss)

**Intro**
> "Eight lights went dark. The ninth kept its promise."
> "You are the promise breaking."

**Phase lines**
- 3 lamps lit: The Warden is weakened; its salt skin cracks; it speaks with the Keeper's
  voice.
- 50% HP: "The town is a memory. The memory is a town. Let it be both."
- 25% HP: "The girl is a memory too. You cannot take her out of the water."
- Defeat: The Warden sinks. The anchor is free.

**The Lantern Anchor**
▸ The Anchor is a ring of black iron with a lens of sea-glass. It is warm. It fits your
hand. The moment you lift it, the town above you exhales.

**DAUGHTER (voice)**
> "You found it. Good."
> "I can't come up there yet. The anchor has to remember me first. Light the districts.
> I'll find you."

`[quest: Q5b complete]` → Act 4.

---

## 20a. The Ascent

▸ The Sanctum stairs go up. The truth town is waiting. Four district shrines glow, one in
each ruined quarter. The Anchor is in your hand.

**DAUGHTER**
> "Four memories. Four lights. You can take them in any order. I'll be there when the last
> one burns."

`[quest: Q6]` → Act 4.

---

# Act 4 — The Light

## 21. The Lit Streets (Q6)

▸ The truth town. The Anchor in your hand. Four district shrines glow, one in each
ruined quarter. The Daughter's voice moves through the streets like a tide.

**DAUGHTER**
> "Four memories. Four lights. You can take them in any order. I'll be there when the
> last one burns."

### 21a — Harbor Shrine: "The Last Ship"

▸ The harbour is full of salt and broken masts. The shrine is a ship's bell.

**Memory (Keeper's voice)**
> "The Ninth Tide took the harbour first. The boats. The nets. Everyone."
> "The last ship was ours. The Saltwake. She went down in sight of the light."
> "My wife begged me to let them go. I said the light would keep them."
> "She said, 'Then the light is the only one who gets to sleep.'"

**Warden: Drowned Sailor**
> "No passage. No freight. No questions."

**After**
▸ The bell rings. The harbour lights. A salvage shop opens in a ruined chandlery.
`[quest: harbor lit]`

### 21b — Market Shrine: "The Last Market Day"

▸ The market is bone stalls and wind. The shrine is a bread oven, cold.

**Memory (Keeper's voice)**
> "It was her birthday. The day before the wreck. She wanted a fish-shaped loaf."
> "The baker made one. She carried it to the dock and fed it to the gulls."
> "I told her the gulls would remember her. I was right. They do."
> "The festival was tomorrow. The wave was tomorrow. No one knew."

**Warden: Hollow Merchant**
> "Same bread. Same coin. Same morning."

**After**
▸ The oven lights. The forge opens in the old smithy.
`[quest: market lit]`

### 21c — Residential Shrine: "The Night of the Wreck"

▸ The lane is roofless. The shrine is a child's window.

**Memory (Keeper's voice)**
> "She was on the dock when the ship broke. I saw her. I could not reach her."
> "I asked the light to keep her. It kept the morning instead."
> "She came back. She was still wet. She said, 'Father, the water is cold.'"
> "The wave took the lane. The children. The old woman at the window. All of them."

**Warden: Weeping Mother**
> "She is still in the water. She is still in the water."

**After**
▸ The window lights. The inn opens in the roofless house.
`[quest: residential lit]`

### 21d — Temple Shrine: "The Lullaby"

▸ The temple is open to a sky with no stars. The shrine is a brass bowl.

**Memory (Keeper's voice / the choir)**
> "The town agreed. That is the part no one says."
> "They knew the morning was a lie. They chose it anyway."
> "The Ninth Tide was the lullaby breaking. The town chose the dream instead."
> "The light sang, and the town slept, and the Sleeper slept under the song."
> "We are the lullaby. We are the thing that keeps the dream asleep."

**Warden: The Choir**
> "Sleep. Sleep. The morning is warm."

**After**
▸ The bowl lights. The memorial opens; the town's names are readable at last.
`[quest: temple lit]`

### 21e — The lit services

Each service opens only when its district is lit. They are real now — the dream is no
longer pretending.

**Salvage shop (Harbor)**
> "Everything the sea took, I take back. Mostly."
> Stock: `wreck_salt`, `beacon_glass`, `siren_pearl`, `salt_iron`; one rotating island
> unique. Buy / sell / ask about the town.

**Forge (Market)**
> "The old smithy. The fire's still good. The smith isn't."
> Options: temper/upgrade, craft the island gear, ask about the lamp.

**Inn (Residential)**
> "Beds are clean. Dreams are extra."
> Real rest. The Daughter sits by the window and, for once, does not watch the water.

**Memorial (Temple)**
> "Say a name. The town remembers."
> Options: read the names, leave a token, ask about the Keeper. Reading all four
> districts' names fills the Town Ledger.

**Beacon (Lighthouse)**
> "The light is a door now. It opens both ways."
> Fast travel to the departure port; post-arc repeatable night raids.

**DAUGHTER (when all four are lit)**
> "I remember me now. All of me."
> "The lighthouse is open. He's waiting."

`[quest: Q6 complete]`

---

## 22. The Lighthouse — Last Light (Q7)

▸ The lighthouse stairs are whole again. The Keeper waits at the top. He is not
smiling. He looks like a man at the end of a long shift.

**KEEPER**
> "You lit the town. You remembered it. You gave it back to itself."
> "I couldn't do that. I could only keep it."
> "I'm tired. I've been tired for a long time."

**Menu**
1) "You can let go." ↳ `KEEPER:` "I don't know how. You'll have to show me."
2) "The town can choose." ↳ `KEEPER:` "Then let them choose. I'm done choosing for
   them." `[flag: keeper_let_go]`
3) "I'm sorry." ↳ `KEEPER:` "Don't be. You noticed. That's more than I did."

**The last fight**
▸ The Keeper does not reach for a weapon. The lighthouse does it for him. The beam
bends down like a blade. He is already at the edge; the fight is the last thing holding
him up.

**KEEPER (during the fight)**
> "I don't want to hurt you."
> "I don't want to be alone."
> "I don't want the morning to end."

**After the fight**
▸ The Keeper is on the floor. The light is in his hands, and then it is not. He is
breathing, but only just. Every ending breaks him here. What differs is what he sees.

**The choice**
1) **Keep the Lullaby** — "Let the light burn. Let the town stay."
2) **End the Lullaby** — "Let the light go out. Let them rest."
3) **Break the Loop** — "Bind the dream to the anchor. Let them choose." *(requires the
   full Town Ledger; triggers the chase)*

`[quest: choose]`

---

## 23. The Chase — "The Last Reset" (true-ending route)

**Beat 1 — The Harbor Gate**
▸ The streets fold. The lighthouse beam sweeps backward. The Daughter's hand is warm.
**DAUGHTER:** "Don't look at the water. Look at me."
- High road (DEX) / tide road (WIS) / follow her hand (safe if trusted).
- Fail: "The street folds the wrong way. You lose a breath."

**Beat 2 — The Market**
▸ The market is full of people who are not there. They are all facing the lighthouse.
**KEEPER (echo):** "The day is not finished."
- Ring the Lullaby Bell / fight through (2-round hold-off) / hide (costs a breath).
- The Daughter: "They're not trying to stop you. They're trying to remember you."

**Beat 3 — The Residential Window**
▸ The Keeper's house. The window is lit. Two shadows inside: a man and a girl.
**DAUGHTER:** "That's us. Before. You can't save them. You can only remember them."
- Save the Ledger / save the ribbon / both (stat check; failure costs a breath; flavor).

**Beat 4 — The Temple Choir**
▸ The choir is the whole town. The song is the reset. The Daughter is singing with them.
**CHOIR:** "Sleep. Sleep. The morning is warm."
- Read the full Town Ledger aloud (requires all four memories) / cover your ears (costs
  two breaths) / let the Daughter sing (high trust).
- Success: "The song breaks. The morning is a morning. It ends."

**Beat 5 — The Lighthouse Stair**
▸ The stairs are falling. The Keeper's echo holds the door.
**KEEPER (echo):** "Go. I'll hold it. I always held it."
- Hold-the-door check / short combat. The Daughter pulls you through.
- At zero breaths: restart at the last beat with "The dream almost caught you."

**Arrival**
▸ The top of the lighthouse. The Keeper is there, broken, smiling. The anchor is in your
hand. The dawn is a thin line on the water.

---

## 24. Endings (Q8)

### A — Keep the Lullaby

▸ The light burns. The town returns — warm, busy, forever tomorrow. The Keeper dies
believing it worked. The Daughter stays in the water, watching the festival she cannot
join.

**KEEPER (epilogue)**
> "There. The morning is still here. Thank you."
> "Tell her I'm sorry. Tell her I kept it as long as I could."

**DAUGHTER (epilogue)**
> "He's at peace. That's one of us."
> "You can visit. The bread is always warm. That's the cruel part."

`[ending: keep]` — island becomes a hidden dream-hub.

### B — End the Lullaby

▸ The light goes out. The town exhales once, and is gone. The Keeper dies as the dream
ends. The Daughter is free — and then she is not there. The sea is just sea.

**KEEPER (epilogue)**
> "Oh. It's quiet."
> "It's been quiet for a long time, hasn't it?"

**DAUGHTER (epilogue)**
> "I was so tired. I didn't know how tired."
> "Don't remember me as the girl on the dock. Remember me as the one who noticed."

`[ending: release]` — island becomes a real, empty memorial.

### C — Bind the Dream

▸ The anchor takes the dream and gives it a shape that can be chosen. The town remains,
but it is no longer a loop: the dead may stay or go. The Keeper dies at peace as the
beacon anchors. **Marian** can leave with you.

**KEEPER (epilogue)**
> "You gave them a choice. I never could."
> "That's better. That's better than keeping them."

**DAUGHTER (epilogue)**
> "I can hear the sea. Not the memory of it. The sea."
> "I think I'd like to see a morning that ends."
> "I'll need a body that isn't made of remembering. This will do." *(her spectral
> full-body gear solidifies — the same kit she wore in the dream, now permanent)*

`[ending: bind]` — island becomes a true waystation; Marian becomes a permanent ally.

---

# Quest ↔ scene ↔ flag map

| Quest | Scenes | Key flags / objectives |
|---|---|---|
| Q0 Ferry | 1 | `lantern_journey_started` |
| Q1 First Day | 2–4 | `lamp_key`, `dock_girl_seen`, `festival_offered` |
| Q1a Residential Clue | 5 | `clue_parts`, `clue_lighthouse`, `clue_daughter`, `clue_correct_loop` |
| Q1b Festival Lamp | 6–8, 10a | `has_oil`, `has_wick`, `has_flame`, `market_granary_cleared`, `festival_lit` → Act 1 reset; in Act 2 the same completion is a wrong loop |
| Q2 You Noticed | 9–10 | `daughter_joined`, `daughter_truth`, `keeper_denial` |
| Q3 What the Town Remembers | 11–14 | `correct_loop_oil`, `correct_loop_wick`, `market_granary_cleared`, `correct_loop_flame` |
| Q4 The Wreck | 15 | `has_lens`, `wreck_cleared` |
| Q4a Dream-Warden | 16–17 | `act2_epilogue_seen`, `dream_warden_defeated` → Act 3 reset |
| Q5 The Unlit Town | 18, 18a–18e | `truth_key_log`, `truth_key_ribbon`, `truth_key_memorial`, `truth_key_flame`, `marian_named` |
| Q5a The Drowned Stair | 19–19b | `sanctum_lamp_1`, `sanctum_lamp_2`, `sanctum_lamp_3` |
| Q5b The Anchor Warden | 20–20a | `anchor_warden_defeated`, `lantern_anchor` |
| Q6 Lit Streets | 21 | `harbor_lit`, `market_lit`, `residential_lit`, `temple_lit` |
| Q7 Last Light | 22–23 | `keeper_defeated`, `lantern_choice` |
| Q8 What Remains | 24 | `ending_keep` / `ending_release` / `ending_bind` |

# Keeper dialogue matrix (quick reference)

| Encounter | Mask | What he says | What it means |
|---|---|---|---|
| First meeting (Act 1) | Gracious host | "The lamp must burn before the festival." | He is feeding the loop |
| Festival completion (Act 1) | Relieved | "There. The day is done." | He knows what the reset is |
| Act 2 first meeting | Pretends amnesia | "Did we? I don't remember." | Denial |
| Wrong loop 1 | Cheerful | "Back so soon? The lamp is waiting." | He is stalling |
| Wrong loop 2 | Tired | "You keep doing the same thing. So do I." | The mask thins |
| Wrong loop 3 | Sharp | "Don't listen to her. She's not real." | He is the one in denial |
| Correct loop 1 (oil) | Watchful | "You stopped. Why did you stop?" | He sees the method |
| Correct loop 2 (wick) | Wounded | "One part. Always one part. You are cruel." | He understands the cost |
| Correct loop 3 (flame) | Almost proud | "The lamp will not be lit. You know that now." | He lets go a little |
| Act 2 epilogue | Confessional | "I asked it to keep them. It kept the town. All of it." | The whole island is the dream |
| Ninth Tide reveal | Confessional | "The town drowned. All of it. I kept all of it." | The Leviathan was always the dreamer; the lens made the dream specific |
| Dream-Warden | The dream's voice | "The day is not finished." | The loop's immune response |
| Act 3 echoes | Absent / echo | "I only wanted the morning to last." | Guilt |
| District memories | Remembered | His wife, his daughter Marian, the town's choice | The life behind the loop |
| Finale | Broken | "I'm tired. I've been tired for a long time." | The end |
| Endings | Epilogue | "Thank you" / "It's quiet" / "You gave them a choice." | What he sees last |
