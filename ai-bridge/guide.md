<!--
공략 문서 (실험 설정에서 "공략 제공"을 고르면 AI에게 전달됨)
버전: guide v2 · 2026-11-04 · 영어 본문 + 게임 화면의 한국어 이름
출처: 이 저장소의 게임(Shattered Pixel Dungeon v4.0.2) 설명문(core/src/main/assets/messages, GPL-3.0, 영어·한국어)과
      게임 코드의 수치(actors/mobs/*.java, MobSpawner.java, npcs/Ghost.java)를 요약. 외부 위키 글은 쓰지 않음.
범위: 1~5층(하수도)과 5층 보스 "구"만.
이전 버전(guide v1, 10/14 한국어 초안)으로 돌린 "공략 제공" 판: run_20261102_192529_player, run_20261104_111303_player
이 파일을 바꾸면 위 버전과 날짜를 올리고, config.json으로 어떤 버전으로 돌린 판인지 구분할 것.
-->
# Guide: Sewers (floors 1-5) and the boss Goo

The game is shown in Korean. Names are written as `English (한국어 화면 이름)`. Match the Korean name with what you see on screen.

## 0. Basics
- To go deeper, find the DOWN stairs (내려가는 계단). One per floor, usually in a different room from where you start.
- On floor 1, the UP stairs (올라가는 계단) is the dungeon entrance. You cannot leave yet. Stepping on it only shows a "you can't leave yet" message.
- No stairs in sight: first explore doors and corridors you have not visited. If everything is explored, search (탐색) next to dead ends and blank walls to find hidden doors.
- Turn-based: enemies act only when you act. No need to hurry.
- HP regenerates slowly while resting. Rest when no enemy is visible.
- Tall grass blocks sight. Walking through it flattens it.
- Water puts out burning (연소) and washes off caustic ooze (산성 점액).
- Dew (이슬) heals a little when picked up. A waterskin (가죽 물통) stores dew for later.
- Iron key (쇠 열쇠) opens a locked door on the same floor. Golden key (황금 열쇠) opens a locked chest.
- Ankh (앙크) revives you once when you die.

## 1. Enemies
Format: floors · HP · damage per hit · trait → how to fight

- Marsupial rat (주머니쥐): floors 1-3 · HP 8 · 1-4 · weak, dangerous only in groups → fight one at a time in a corridor
- Albino rat (알비노 쥐), rare: floors 1-3 · HP 12 · bite causes bleeding → fight with spare HP
- Sewer snake (하수구 뱀): floors 1-3 · HP 4 · 1-4 · dodges most attacks → lure it through a door and hit it right after it steps through. Hitting it while it cannot see you is a sneak attack
- Gnoll scout (놀 정찰병): floors 2-5 · HP 12 · 1-6 · stronger than rats → rest to full before fighting if HP is under half
- Swarm of flies (파리떼): floors 3-5 · HP 50 total · 1-4 · flies, splits in two on every non-magic hit → fight in a 1-tile-wide corridor so only one swarm reaches you
- Sewer crab (하수구 게): floors 3-5 · HP 15 · 1-7 · moves twice as fast, tough shell → you cannot outrun it. Heal up and fight
- Slime (슬라임): floors 4-5 · HP 20 · 2-5 · takes at most about 6 damage per hit → weak attacks work as well as strong ones. Keep hitting
- Caustic slime (산성 슬라임), rare: floors 4-5 · like slime, hits apply caustic ooze → wash in water
- Crazy thief (미치광이 도둑), rare: floor 4 · HP 20 · 1-10 · steals an item and runs → kill it before it escapes. It drops the stolen item on death
- Mimic (미믹): any floor · looks like a chest (상자) → have full HP before opening chests

### Sad ghost (슬픈 유령), may appear on floors 2-4
- Talk to it. It asks you to kill one special enemy and gives a weapon or armor as a reward.
- The enemy depends on the floor:
  - Floor 2 · Fetid rat (악취나는 쥐), HP 20: applies caustic ooze → fight near water, avoid its stench cloud
  - Floor 3 · Gnoll trickster (놀 사기꾼), HP 20: throws poison/fire darts from range → close the distance, fight adjacent
  - Floor 4 · Great crab (거대한 게), HP 25: blocks attacks from the front with its claw → sneak attack, or attack from several sides at once

## 2. Boss: Goo (구), floor 5, HP 100
- Pump up: message "구가 스스로의 몸집을 불리기 시작했다!" and it swells. When charged, it hits for 3x normal damage and reaches up to 2 tiles away in a straight, unblocked line.
  → When you see the message, get 3+ tiles away or behind a wall/corner. Re-engage after the attack.
- Standing in water, Goo heals every turn → pull it onto dry ground before fighting.
- Below half HP it hits harder and pumps up more often.
- Its hits sometimes apply caustic ooze → wash in water, but don't let Goo follow you into water.
- Before entering the boss room: full HP. Save healing potions for this fight.

## 3. Status effects
Format: effect → what to do

- Poisoned (중독): damage every turn, more with longer duration → healing potion
- Burning (연소): damage every turn, fire spreads → step into water
- Bleeding (출혈): damage every turn, fades over time → wait it out or healing potion
- Caustic ooze (산성 점액): damage every turn → step into water, removed at once
- Paralysed (마비): cannot act → avoid paralytic gas
- Rooted (속박): cannot move, other actions OK → fight where you stand
- Crippled (불구): moves at half speed → fight instead of fleeing
- Weakened (약화): deals 33% less damage → avoid fights until it ends
- Blinded (실명): sight is 1 tile → rest until it ends
- Vertigo (현기증): moves go in random directions → don't move until it ends
- Hungry (배고픔) → Starving (굶주림): starving stops HP regen and drains HP → eat when "배고픔" appears
- Good effects: levitating (부유, ignore traps and chasms), invisible (투명화, enemies can't see you, broken by attacking), haste (신속, move 3x faster), healing (치유 중), mind vision (심안, see all creatures on the floor), barkskin (나무껍질, more armor)

## 4. Items
### Potions (물약)
- Unknown potions show only a color, e.g. "주황색 물약". Color-to-effect pairs change every game.
- Drinking or throwing one identifies that color for the rest of the game.
- Test unknown potions where no enemy is near and water is nearby, ideally at full HP.
- Good to drink: healing (치유), strength (힘, +1 strength permanently), experience (경험, +1 level), mind vision (심안), levitation (부유), invisibility (투명화), haste (신속), purity (정화)
- Harmful to drink, throw at enemies instead: toxic gas (유독 가스, poison), liquid flame (액체 화염, fire), frost (서리, freezing), paralytic gas (마비 가스, paralysis)

### Scrolls (주문서)
- Unknown scrolls show only a rune name. Reading one identifies it.
- Good: upgrade (강화, upgrades one weapon or armor), identify (감정, reveals one item), remove curse (저주 해제), magic mapping (마법 지도, reveals the floor layout and hidden doors, great for finding stairs), recharging (충전), mirror image (거울상, two decoys)
- Situational: teleportation (공간이동, random spot on the floor), transmutation (변환, changes an item into another of the same kind), lullaby (자장가, puts nearby creatures to sleep), terror (공포, visible enemies flee), retribution (징벌, stronger the lower your HP)
- Careful: rage (분노) calls every enemy on the floor to you. Don't read unknown scrolls when many enemies are around.

### Equipment
- Weapons and armor need a strength value. With too little strength, movement, dodging and defense drop.
- Unidentified equipment can be cursed. Cursed equipment cannot be removed (use remove curse).
- Put upgrade scrolls into the one weapon or armor you use most.

### Food
- Ration (비상식량), small ration (소형 비상식량), pasty (패스티): fill hunger.
- Dungeon berry (작은 던전 열매): fills a little hunger.
- Mystery meat (수상한 고기): may cause bad effects. Eat only if nothing else.
