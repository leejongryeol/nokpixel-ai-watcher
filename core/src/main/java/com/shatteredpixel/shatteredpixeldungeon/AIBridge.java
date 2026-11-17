/*
 * Pixel Dungeon
 * Copyright (C) 2012-2015 Oleg Dolya
 *
 * Shattered Pixel Dungeon
 * Copyright (C) 2014-2026 Evan Debenham
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>
 */

package com.shatteredpixel.shatteredpixeldungeon;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.Input;
import com.badlogic.gdx.Net;
import com.badlogic.gdx.utils.JsonReader;
import com.badlogic.gdx.utils.JsonValue;
import com.badlogic.gdx.utils.JsonWriter;
import com.shatteredpixel.shatteredpixeldungeon.actors.Actor;
import com.shatteredpixel.shatteredpixeldungeon.actors.Char;
import com.shatteredpixel.shatteredpixeldungeon.actors.hero.HeroAction;
import com.shatteredpixel.shatteredpixeldungeon.actors.hero.Hero;
import com.shatteredpixel.shatteredpixeldungeon.actors.mobs.Goo;
import com.shatteredpixel.shatteredpixeldungeon.actors.mobs.Mimic;
import com.shatteredpixel.shatteredpixeldungeon.actors.mobs.Mob;
import com.shatteredpixel.shatteredpixeldungeon.items.Amulet;
import com.shatteredpixel.shatteredpixeldungeon.items.Heap;
import com.shatteredpixel.shatteredpixeldungeon.items.Item;
import com.shatteredpixel.shatteredpixeldungeon.items.potions.Potion;
import com.shatteredpixel.shatteredpixeldungeon.items.rings.Ring;
import com.shatteredpixel.shatteredpixeldungeon.items.scrolls.Scroll;
import com.shatteredpixel.shatteredpixeldungeon.levels.Level;
import com.shatteredpixel.shatteredpixeldungeon.levels.Terrain;
import com.shatteredpixel.shatteredpixeldungeon.levels.features.LevelTransition;
import com.shatteredpixel.shatteredpixeldungeon.messages.Messages;
import com.shatteredpixel.shatteredpixeldungeon.scenes.AICreditsScene;
import com.shatteredpixel.shatteredpixeldungeon.scenes.GameScene;
import com.shatteredpixel.shatteredpixeldungeon.scenes.InterlevelScene;
import com.shatteredpixel.shatteredpixeldungeon.scenes.PixelScene;
import com.shatteredpixel.shatteredpixeldungeon.scenes.RankingsScene;
import com.shatteredpixel.shatteredpixeldungeon.scenes.TitleScene;
import com.shatteredpixel.shatteredpixeldungeon.utils.DungeonSeed;
import com.shatteredpixel.shatteredpixeldungeon.utils.GLog;
import com.shatteredpixel.shatteredpixeldungeon.windows.WndAIGoal;
import com.watabou.noosa.Game;
import com.watabou.noosa.Scene;
import com.watabou.utils.Callback;
import com.watabou.utils.DeviceCompat;
import com.watabou.utils.Signal;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedList;

//[nokpixel-ai-watcher] 게임 → AI 관찰기(ai-bridge/web.py) 통로 (docs/project/bridge.md 3장)
//게임이 묻고 Python이 답한다. 응답은 다른 스레드에서 오므로 렌더 스레드로 넘겨서 돌려준다.
//실패, 시간 초과, 이상한 응답은 모두 null로 돌려준다. 어떤 경우에도 게임을 멈추거나 끄지 않는다.
public class AIBridge {

	public static final String HOST = "http://127.0.0.1:8765";
	public static final int SHORT_TIMEOUT = 3000; //상태 조회·키 보내기·판 준비 (ms)
	public static final int TEST_TIMEOUT = 35000; //연결 시험: Python이 최대 30초 + 여유

	//AI 판 표시 (bridge.md 9장 A-5-4)
	//pendingRunId: AI 설정 장면의 [AI로 시작]이 판 준비(④)에 성공했을 때만 켠다. 그 뒤 첫 던전 도착에서 한 번 쓰고 지운다
	//activeRunId: 던전 도착(⑤)이 성공해서 AI가 플레이하는 판
	public static String pendingRunId = null;
	public static String activeRunId = null;

	private static final float ARRIVE_DELAY = 1.2f; //화면이 밝아지는 효과(1초)가 끝난 뒤에 알린다
	private static Scene arrivalScene;
	private static float arrivalTime;

	//⑦ 살아 있음 신호: AI 판이 GameScene에 있는 동안 1초마다. Python은 키를 보내기 직전마다 이 신호를 확인한다
	private static final float HEARTBEAT_EVERY = 1f;
	private static final int HEARTBEAT_FAILS = 3; //연달아 이만큼 실패하면 관찰기가 꺼진 것으로 보고 AI 판 표시를 지운다
	private static float sinceHeartbeat;
	private static boolean heartbeatInFlight;
	private static boolean deathSent;
	private static int heartbeatFails;

	//⑧ 상태 보내기 (docs/project/game-state.md, A-6-2): 주인공이 입력을 기다리게 될 때마다 한 번
	private static final int LOG_LINES = 8; //마지막 상태 뒤에 나온 메시지를 이만큼까지 모은다
	private static int stateSeq;
	private static Scene stateScene;
	private static boolean wasWaiting;
	private static int prevDepth, prevHP;
	private static HashSet<Integer> prevEnemies = new HashSet<>(); //직전 상태에 보이던 적 (비교에만 쓰고 밖으로 보내지 않는다)
	private static Item prevWeapon, prevArmor;
	private static int equipChanges;
	private static Goo goo; //5층 보스 (이정표 기록용)
	private static boolean gooSeen, gooDead;
	private static final LinkedList<JsonValue> logLines = new LinkedList<>();

	//최종 목표 달성 판정용 (A-6-4). ⑧ record로만 보내고 AI 입력에는 넣지 않는다
	private static boolean doorPassed; //0단계: 주인공이 문 칸에 처음 들어섬
	private static final ArrayList<Integer> bossesSlain = new ArrayList<>(); //1~5단계: 보스를 처치한 층 (5·10·15·20·25)

	//⑨ 명령 받기 (A-6-5, game-state.md 3장·4장): 주인공이 입력을 기다리는 동안 0.5초마다 Python에 묻는다
	private static final float COMMAND_EVERY = 0.5f;
	private static float sinceCommand;
	private static boolean commandInFlight;
	private static boolean wantCommand; //마지막 ⑧ 응답의 want_command (Python이 명령 도구를 쓰는 판인지)
	private static int commandAskedSeq; //이 상태 번호로는 명령을 이미 받아 처리함 (다음 상태까지 묻지 않는다)
	private static int lastCommandSeq = -1; //마지막으로 처리한 명령의 seq (같은 seq는 한 번만)
	private static JsonValue lastCommand; //다음 ⑧의 last_command로 보낼 값

	//달성 창 (A-6-6): ⑦·⑧ 응답의 goal_wait로 띄운다. 같은 번호의 창은 한 번만 띄운다
	private static int goalWindowId;

	//게임 메시지(GLog)를 모은다. 액터 스레드에서도 불리므로 잠근다. false를 돌려 화면 기록창도 그대로 받게 한다
	private static final Signal.Listener<String> logListener = new Signal.Listener<String>() {
		@Override
		public boolean onSignal( String text ) {
			collectLog(text);
			return false;
		}
	};

	//GameScene.update()에서 매 프레임 불린다
	public static void onGameUpdate(){
		try {
			if (pendingRunId != null) checkArrival();
			if (activeRunId != null) {
				//화면 기록창(GameLog)은 새로 만들어질 때 replace()로 다른 듣는 쪽을 모두 지운다 (층 이동·이어하기).
				//add()는 이미 붙어 있으면 아무것도 하지 않으므로, 매 프레임 불러 지워졌으면 다시 붙인다
				GLog.update.add(logListener);
				checkDoor();
				checkSimulateKey();
				checkWaiting();
				pollCommand();
				heartbeat();
			} else {
				GLog.update.remove(logListener);
			}
		} catch (Exception e) {
			Game.reportException(e);
		}
	}

	private static void resetState(){
		stateSeq = 0;
		stateScene = null;
		wasWaiting = false;
		prevDepth = -1;
		prevHP = 0;
		prevEnemies = new HashSet<>();
		prevWeapon = prevArmor = null;
		equipChanges = 0;
		goo = null;
		gooSeen = gooDead = false;
		doorPassed = false;
		synchronized (bossesSlain) { bossesSlain.clear(); }
		sinceCommand = 0;
		wantCommand = false;
		commandAskedSeq = 0;
		lastCommandSeq = -1;
		lastCommand = null;
		goalWindowId = 0;
		synchronized (logLines) { logLines.clear(); }
	}

	//문 칸에 들어선 것을 매 프레임 확인한다. 여러 칸을 한 번에 가는 이동 중에 지나가도 놓치지 않게 상태(⑧)를 보낼 때가 아니라 여기서 본다
	private static void checkDoor(){
		if (doorPassed || Dungeon.hero == null || Dungeon.level == null) return;
		int pos = Dungeon.hero.pos;
		if (pos < 0 || pos >= Dungeon.level.length()) return;
		int t = Dungeon.level.map[pos];
		if (t == Terrain.DOOR || t == Terrain.OPEN_DOOR) doorPassed = true;
	}

	//GameScene.bossSlain()에서 불린다 (보스가 쓰러질 때). 본 던전(branch 0)의 5층마다 보스만 센다. 갈래 퀘스트 보스는 뺀다
	public static void onBossSlain(){
		if (activeRunId == null) return;
		int depth = Dungeon.depth;
		if (Dungeon.branch != 0 || depth % 5 != 0 || depth < 5 || depth > 25) return;
		synchronized (bossesSlain) {
			if (!bossesSlain.contains(depth)) bossesSlain.add(depth);
		}
	}

	private static void collectLog( String text ){
		if (text == null || text.equals(GLog.NEW_LINE)) return;
		String kind = "normal";
		if (text.startsWith(GLog.POSITIVE)) { kind = "good"; text = text.substring(GLog.POSITIVE.length()); }
		else if (text.startsWith(GLog.NEGATIVE)) { kind = "bad"; text = text.substring(GLog.NEGATIVE.length()); }
		else if (text.startsWith(GLog.WARNING)) { kind = "warning"; text = text.substring(GLog.WARNING.length()); }
		else if (text.startsWith(GLog.HIGHLIGHT)) { kind = "highlight"; text = text.substring(GLog.HIGHLIGHT.length()); }
		text = text.trim();
		if (text.isEmpty()) return;
		JsonValue line = object();
		line.addChild("kind", new JsonValue(kind));
		line.addChild("text", new JsonValue(text));
		synchronized (logLines) {
			logLines.add(line);
			while (logLines.size() > LOG_LINES) logLines.removeFirst();
		}
	}

	//주인공이 입력을 기다리게 된 순간(거짓→참), 또는 GameScene이 새로 생긴 뒤 처음 기다릴 때 상태를 보낸다
	private static void checkWaiting(){
		Scene scene = Game.scene();
		if (scene != stateScene) {
			stateScene = scene;
			wasWaiting = false;
		}
		Hero hero = Dungeon.hero;
		boolean waiting = hero != null && hero.isAlive() && hero.ready && hero.curAction == null && Dungeon.level != null
				&& InterlevelScene.mode == InterlevelScene.Mode.NONE;
		if (waiting && !wasWaiting) sendState(false);
		wasWaiting = waiting;
	}

	//rejected: 명령을 실행하지 않아 주인공이 같은 대기에 그대로 있을 때. 이유는 rejected 하나로 보낸다 (3-3)
	private static void sendState( boolean rejected ){
		Hero hero = Dungeon.hero;
		ArrayList<JsonValue> log;
		synchronized (logLines) {
			log = new ArrayList<>(logLines);
			logLines.clear();
		}
		JsonValue ai = GameState.build(log);

		//보이는 적 (정체 전 미믹 제외)
		HashSet<Integer> enemies = new HashSet<>();
		for (Mob m : Dungeon.level.mobs.toArray(new Mob[0])){
			if (GameState.seenChar(m, Dungeon.level) && m.alignment == Char.Alignment.ENEMY && !(m instanceof Mimic && m.alignment == Char.Alignment.NEUTRAL)){
				enemies.add(m.id());
			}
		}

		//끝난 이유 (game-state.md 3-3). Hero는 고치지 않고 직전 상태와 비교해서 정한다
		JsonValue reasons = GameState.array();
		if (rejected) {
			reasons.addChild(new JsonValue("rejected"));
		} else if (prevDepth < 0) {
			reasons.addChild(new JsonValue("start"));
		} else {
			if (Dungeon.depth != prevDepth) {
				reasons.addChild(new JsonValue("level_changed"));
			} else {
				for (Integer id : enemies) {
					if (!prevEnemies.contains(id)) { reasons.addChild(new JsonValue("interrupted_enemy")); break; }
				}
				if (hero.HP < prevHP) {
					//게임이 화면을 빨갛게 번쩍이는 식과 같다 (Hero.damage)
					float percentDMG = (prevHP - hero.HP) / (float)prevHP;
					float percentHP = hero.HP / (float)hero.HT;
					boolean heavy = percentHP > 0 && 0.25f * percentDMG * percentDMG / percentHP >= 0.05f;
					reasons.addChild(new JsonValue(heavy ? "damaged_heavy" : "damaged"));
				}
			}
			if (hero.lastAction != null) reasons.addChild(new JsonValue("interrupted"));
			if (GameScene.interfaceBlockingHero()) reasons.addChild(new JsonValue("window"));
			if (reasons.size == 0) reasons.addChild(new JsonValue("done"));
		}
		prevDepth = Dungeon.depth;
		prevHP = hero.HP;
		prevEnemies = enemies;

		JsonValue body = object();
		body.addChild("state_version", new JsonValue(GameState.VERSION));
		body.addChild("run_id", new JsonValue(activeRunId));
		body.addChild("seq", new JsonValue(++stateSeq));
		body.addChild("reasons", reasons);
		//바로 앞 명령과 그 결과 (A-6-5). 명령이 없었으면 null. 한 번 보내면 지운다
		body.addChild("last_command", lastCommand != null ? lastCommand : new JsonValue(JsonValue.ValueType.nullValue));
		lastCommand = null;
		body.addChild("ai", ai);
		body.addChild("record", record(hero));
		final String runId = activeRunId;
		post("/api/bridge/state", body, SHORT_TIMEOUT, new Listener() {
			@Override
			public void onResult(JsonValue result) {
				//실패하면 버린다. 다음 대기 때 새 상태를 보낸다
				if (result != null && runId.equals(activeRunId)) {
					wantCommand = result.getBoolean("want_command", false);
					showGoalWindow(result);
				}
			}
		});
	}

	//⑨ 명령 받기: 주인공이 이 상태의 대기 그대로인 동안 0.5초마다. 앞 요청이 돌아오기 전에는 묻지 않는다
	private static void pollCommand(){
		if (!wantCommand || !wasWaiting || stateSeq == 0 || commandAskedSeq == stateSeq) return;
		sinceCommand += Game.elapsed;
		if (commandInFlight || sinceCommand < COMMAND_EVERY) return;
		sinceCommand = 0;
		final String runId = activeRunId;
		JsonValue body = object();
		body.addChild("run_id", new JsonValue(runId));
		body.addChild("seq", new JsonValue(stateSeq));
		commandInFlight = true;
		post("/api/bridge/command", body, SHORT_TIMEOUT, new Listener() {
			@Override
			public void onResult(JsonValue result) {
				commandInFlight = false;
				if (result == null || !runId.equals(activeRunId)) return;
				JsonValue c = result.get("command");
				if (c != null && c.isObject()) runCommand(c);
			}
		});
	}

	//받은 명령을 확인하고(3-2) 실행한다. 걸리면 아무것도 하지 않고 rejected 상태로 알린다
	private static void runCommand( JsonValue c ){
		int seq = c.getInt("seq", -1);
		if (seq == lastCommandSeq) return; //같은 명령은 한 번만
		lastCommandSeq = seq;
		commandAskedSeq = stateSeq;
		String name = c.getString("name", "");
		JsonValue args = c.get("args");
		int x = args != null ? args.getInt("x", Integer.MIN_VALUE) : Integer.MIN_VALUE;
		int y = args != null ? args.getInt("y", Integer.MIN_VALUE) : Integer.MIN_VALUE;
		String until = args != null ? args.getString("until", "turn") : "turn";

		String outcome;
		try {
			outcome = execute(seq, name, x, y, until);
		} catch (Exception e) {
			Game.reportException(e);
			outcome = "error";
		}

		//args는 받은 JSON을 그대로 붙이지 않고 새로 만든다 (다른 트리에 달린 값을 옮기면 망가질 수 있음)
		JsonValue cmd = object();
		cmd.addChild("seq", new JsonValue(seq));
		cmd.addChild("name", new JsonValue(name));
		JsonValue a = object();
		if (x != Integer.MIN_VALUE) a.addChild("x", new JsonValue(x));
		if (y != Integer.MIN_VALUE) a.addChild("y", new JsonValue(y));
		if (name.equals("rest")) a.addChild("until", new JsonValue(until));
		cmd.addChild("args", a);
		cmd.addChild("outcome", new JsonValue(outcome == null ? "ok" : outcome));
		lastCommand = cmd;

		if (outcome == null) {
			wasWaiting = false; //행동이 턴 없이 끝나도(길 없음 등) 다음 대기에서 새 상태를 보낸다
		} else {
			sendState(true); //주인공은 같은 대기 그대로. 새 상태 번호로 실행 안 함을 알린다
		}
	}

	//null이면 실행함. 아니면 실행하지 않은 이유 (game-state.md 3-2 순서)
	private static String execute( int seq, String name, int x, int y, String until ){
		Hero hero = Dungeon.hero;
		Level level = Dungeon.level;
		if (hero == null || !hero.isAlive()) return "dead";
		if (!hero.ready || hero.curAction != null) return "not_ready";
		if (GameScene.interfaceBlockingHero()) return "window_open";
		if (seq != stateSeq) return "stale";

		//칸을 쓰지 않는 명령: 툴바 기다리기(짧게·길게)·탐색과 같은 함수
		if (name.equals("rest")) {
			hero.rest(until.equals("full"));
			return null;
		}
		if (name.equals("search")) {
			hero.search(true);
			return null;
		}
		if (!name.equals("move_to") && !name.equals("attack") && !name.equals("pick_up") && !name.equals("take_stairs")) {
			return "bad_command";
		}

		int cell;
		if (name.equals("pick_up") && x == Integer.MIN_VALUE && y == Integer.MIN_VALUE) {
			cell = hero.pos; //발밑
		} else {
			if (x < 0 || y < 0 || x >= level.width() || y >= level.height()) return "out_of_map";
			cell = x + y * level.width();
		}
		//모르는 칸: 성공·실패만으로 안 본 지형을 알게 되므로 실행하지 않는다
		if (!GameState.shown(level, cell)) return "unknown_cell";

		Char ch = Actor.findChar(cell);
		boolean disguisedChest = ch instanceof Mimic && ch.alignment == Char.Alignment.NEUTRAL && GameState.seenChar(ch, level);
		if (name.equals("attack")) {
			if (!(ch instanceof Mob) || !GameState.seenChar(ch, level) || ch.alignment != Char.Alignment.ENEMY) return "no_enemy";
		} else if (name.equals("pick_up")) {
			Heap heap = level.heaps.get(cell);
			if ((heap == null || !heap.seen || heap.isEmpty()) && !disguisedChest) return "no_item";
		} else if (name.equals("take_stairs")) {
			LevelTransition t = level.getTransition(cell);
			if (t == null) return "no_stairs";
			if (Dungeon.depth == 1 && GameState.isUp(t)) return "cannot_leave";
		}

		//칸 누르기와 같은 경로. 게임이 고른 행동이 명령의 뜻과 다르면 실행하지 않는다
		hero.handle(cell);
		HeroAction act = hero.curAction;
		boolean match;
		if (name.equals("move_to")) {
			//본 적 없는 아이템이 있는 칸이면 게임은 줍기를 고른다. 여기서 막으면 아이템이 있다는 것을 알려 주게 되므로 사람이 누를 때처럼 그대로 한다
			Heap unseen = level.heaps.get(cell);
			match = act instanceof HeroAction.Move
					|| (unseen != null && !unseen.seen && (act instanceof HeroAction.PickUp || act instanceof HeroAction.OpenChest));
		} else if (name.equals("attack")) {
			match = act instanceof HeroAction.Attack;
		} else if (name.equals("pick_up")) {
			//보이는 상자가 정체 전 미믹이면 사람이 눌렀을 때처럼 공격이 된다 (여기서 막으면 미믹인 것을 알려 주게 됨)
			match = act instanceof HeroAction.PickUp || act instanceof HeroAction.OpenChest
					|| (disguisedChest && act instanceof HeroAction.Attack);
		} else {
			match = act instanceof HeroAction.LvlTransition;
		}
		if (!match) {
			hero.curAction = null;
			return "not_this_action";
		}
		hero.next();
		return null;
	}

	//이정표 기록용 값 (docs/project/progress-milestones.md). AI 입력에는 넣지 않는다.
	//정체를 아는 아이템 종류는 숫자만 보낸다 (어떤 아이템인지는 보내지 않는다)
	private static JsonValue record( Hero hero ){
		Item weapon = hero.belongings.weapon(), armor = hero.belongings.armor();
		if (stateSeq > 1 && (weapon != prevWeapon || armor != prevArmor)) equipChanges++;
		prevWeapon = weapon;
		prevArmor = armor;

		int items = 0;
		for (Item item : hero.belongings) items += item.quantity();

		JsonValue r = object();
		r.addChild("enemies_slain", new JsonValue(Statistics.enemiesSlain));
		r.addChild("deepest_floor", new JsonValue(Statistics.deepestFloor));
		r.addChild("hero_lvl", new JsonValue(hero.lvl));
		r.addChild("upgrades_used", new JsonValue(Statistics.upgradesUsed));
		r.addChild("equip_changes", new JsonValue(equipChanges));
		r.addChild("items_total", new JsonValue(items));
		r.addChild("known_types", new JsonValue(Potion.getKnown().size() + Scroll.getKnown().size() + Ring.getKnown().size()));
		r.addChild("door_passed", new JsonValue(doorPassed));
		JsonValue bosses = GameState.array();
		synchronized (bossesSlain) {
			for (Integer d : bossesSlain) bosses.addChild(new JsonValue(d));
		}
		r.addChild("bosses_slain", bosses);

		//5층 보스 구: 한 번이라도 보였는지, 체력 비율, 쓰러졌는지
		if (Dungeon.depth == 5) {
			Goo found = null;
			for (Mob m : Dungeon.level.mobs.toArray(new Mob[0])){
				if (m instanceof Goo) { found = (Goo) m; break; }
			}
			if (found != null && found.isAlive()) {
				goo = found;
				if (Dungeon.level.heroFOV[found.pos]) gooSeen = true;
			} else if (goo != null) {
				gooDead = true; //본 적 있는 구가 층에서 사라졌거나 죽었다
			}
		}
		if (goo != null) {
			JsonValue boss = object();
			boss.addChild("seen", new JsonValue(gooSeen));
			boss.addChild("hp_ratio", new JsonValue(gooDead ? 0.0 : Math.round(100.0 * goo.HP / goo.HT) / 100.0));
			boss.addChild("dead", new JsonValue(gooDead));
			r.addChild("boss", boss);
		} else {
			r.addChild("boss", new JsonValue(JsonValue.ValueType.nullValue));
		}
		return r;
	}

	//⑥ 사망: GameScene.gameOver()에서 불린다
	public static void onGameOver(){
		end("died");
	}

	//⑥ 승리·타이틀로 나가기·게임 종료: GameScene.destroy()에서 불린다
	//층을 옮길 때는 InterlevelScene.mode를 NONE이 아닌 값으로 정한 뒤 장면을 바꾸므로 판 끝이 아니다
	//승리: 아뮬렛을 주우면 바로 아뮬렛 화면으로 넘어가고, gameWon은 그 화면의 [던전을 나간다]에서야 참이 된다.
	//그래서 아뮬렛을 얻은 채 던전 화면을 떠나는 것도 승리로 본다 (A-6-6. AI 판은 1층 새 판에서 시작하고 이때 끝난다)
	public static void onLeaveGame(){
		if (InterlevelScene.mode != InterlevelScene.Mode.NONE) return;
		pendingRunId = null;
		end(Statistics.gameWon || Statistics.amuletObtained ? "won" : "quit");
	}

	private static void end(String reason){
		if (activeRunId == null) return;
		final String runId = activeRunId;
		JsonValue body = object();
		body.addChild("run_id", new JsonValue(runId));
		body.addChild("reason", new JsonValue(reason));
		body.addChild("depth", new JsonValue(Dungeon.depth));
		activeRunId = null; //판이 끝났으므로 신호도 멈춘다. 닿지 않아도 신호가 끊겨서 Python은 키를 보내지 않는다
		post("/api/bridge/ended", body, SHORT_TIMEOUT, new Listener() {
			@Override
			public void onResult(JsonValue result) {
				//결과와 관계없이 게임은 그대로 진행한다. 마지막 최종 목표(엔딩)를 이뤘으면 승리 흐름 뒤에 크레딧을 보인다 (A-6-6)
				if (result != null && result.getBoolean("credits", false)) creditsRunId = runId;
			}
		});
	}

	//엔딩 크레딧 (A-6-6): ⑥ won 응답이 credits면 그 판 번호를 둔다. 아뮬렛 화면 [던전을 나간다] 뒤에 쓴다
	private static String creditsRunId = null;

	//원작 승리 흐름의 다음 장면: 크레딧을 보일 판이면 AICreditsScene, 아니면 원작대로 순위 화면
	public static Class<? extends PixelScene> afterVictory(){
		return creditsRunId != null ? AICreditsScene.class : RankingsScene.class;
	}

	//크레딧 장면이 한 번 가져가고 지운다
	public static String takeCreditsRunId(){
		String id = creditsRunId;
		creditsRunId = null;
		return id;
	}

	private static void heartbeat(){
		if (Dungeon.hero == null) return;
		boolean alive = Dungeon.hero.isAlive();
		sinceHeartbeat += Game.elapsed;
		boolean justDied = !alive && !deathSent;
		if (heartbeatInFlight || (sinceHeartbeat < HEARTBEAT_EVERY && !justDied)) return;
		if (justDied) deathSent = true; //죽은 것을 처음 보면 1초를 기다리지 않고 바로 알린다

		final String runId = activeRunId;
		JsonValue body = object();
		body.addChild("run_id", new JsonValue(runId));
		body.addChild("alive", new JsonValue(alive));
		body.addChild("depth", new JsonValue(Dungeon.depth));
		//마지막으로 보낸 상태 번호와, 주인공이 그 상태를 보낸 대기 그대로인지 (A-6-3).
		//벽에 부딪히기처럼 턴이 안 지나는 입력 뒤에는 새 상태가 없으므로, Python은 이 값으로 마지막 상태가 아직 맞는지 안다
		body.addChild("state_seq", new JsonValue(stateSeq));
		body.addChild("waiting", new JsonValue(wasWaiting));
		sinceHeartbeat = 0;
		heartbeatInFlight = true;
		post("/api/bridge/heartbeat", body, SHORT_TIMEOUT, new Listener() {
			@Override
			public void onResult(JsonValue result) {
				heartbeatInFlight = false;
				if (!runId.equals(activeRunId)) return;
				if (result == null) {
					//관찰기가 꺼졌다. 게임은 그대로 두고 사람이 이어서 할 수 있게 한다
					if (++heartbeatFails >= HEARTBEAT_FAILS) {
						activeRunId = null;
						GLog.w(Messages.get(GameScene.class, "ai_disconnected"));
					}
				} else {
					heartbeatFails = 0;
					//판이 이미 끝났다 (최대 판단, 중지, 관찰기 다시 켬)
					if (!result.getBoolean("ok", false)) {
						activeRunId = null;
						//최종 목표를 이뤄 판을 끝냈다 (A-6-4): 게임 메뉴의 [타이틀로]와 같은 처리로 타이틀 화면에 간다.
						//activeRunId를 먼저 지웠으므로 GameScene.destroy()에서 ⑥(quit)을 보내지 않는다
						if (result.getBoolean("goto_title", false)) goToTitle();
					} else {
						showGoalWindow(result);
					}
				}
			}
		});
	}

	//시험용 달성 흉내 (A-6-6): 개발용 실행(desktop:debug)에서만 F9로 "지금 단계 달성"을 흉내 낸다. 배포용에서는 아무것도 하지 않는다.
	//Python이 흉내로 표시(simulated)해서 기록한다. 엔딩 단계는 원작 아뮬렛 화면을 열어 실제 승리 흐름을 탄다
	private static boolean simulateInFlight;

	private static void checkSimulateKey(){
		if (!DeviceCompat.isDebug() || simulateInFlight || !Gdx.input.isKeyJustPressed(Input.Keys.F9)) return;
		Hero hero = Dungeon.hero;
		if (hero == null || !hero.isAlive() || !hero.ready || !(Game.scene() instanceof GameScene)
				|| GameScene.interfaceBlockingHero()) return;
		final String runId = activeRunId;
		JsonValue body = object();
		body.addChild("run_id", new JsonValue(runId));
		simulateInFlight = true;
		post("/api/bridge/simulate_goal", body, SHORT_TIMEOUT, new Listener() {
			@Override
			public void onResult(JsonValue result) {
				simulateInFlight = false;
				if (result == null || !result.getBoolean("ok", false) || !runId.equals(activeRunId)) return;
				if (result.getBoolean("amulet", false)) {
					simulateAmulet();
				} else {
					showGoalWindow(result);
				}
			}
		});
	}

	//아뮬렛을 주운 것처럼: 얻음 표시(⑥ won 판정)를 하고 아뮬렛의 [끝내기] 동작으로 원작 아뮬렛 화면을 연다 (개발용 실행만)
	private static void simulateAmulet(){
		Hero hero = Dungeon.hero;
		if (!DeviceCompat.isDebug() || hero == null || !hero.isAlive() || !(Game.scene() instanceof GameScene)) return;
		Statistics.amuletObtained = true;
		new Amulet().execute(hero, "END");
	}

	//⑦·⑧ 응답에 goal_wait가 있으면 달성 창을 띄운다 (A-6-6). 던전 화면에서만, 같은 번호는 한 번만
	private static void showGoalWindow( JsonValue result ){
		JsonValue w = result.get("goal_wait");
		if (w == null || !w.isObject() || !(Game.scene() instanceof GameScene)) return;
		int id = w.getInt("id", 0);
		if (id <= goalWindowId) return;
		goalWindowId = id;
		//이어하기 슬롯 화면에 "AI 최종 목표 달성! (이름)"을 보이도록 슬롯마다 기록한다 (저장 파일은 그대로)
		SPDSettings.aiGoalMark(GamesInProgress.curSlot, Dungeon.seed, w.getString("reached", ""));
		GameScene.show(new WndAIGoal(id, w.getString("reached", ""), w.getInt("step", 0), w.getString("next", ""),
				w.getBoolean("simulated", false)));
	}

	//달성 창에서 고른 것을 Python에 보낸다 (⑩). Python이 받지 않으면 다음 ⑦ 응답에 창이 다시 뜨게 한다.
	//[타이틀로]는 Python이 마지막 화면을 찍은 뒤 ⑦ 응답의 goto_title로 간다. 관찰기가 꺼져 있으면 게임이 바로 간다
	public static void goalChoice( final int id, final String choice ){
		final String runId = activeRunId;
		if (runId == null) {
			if (choice.equals("title")) goToTitle();
			return;
		}
		JsonValue body = object();
		body.addChild("run_id", new JsonValue(runId));
		body.addChild("id", new JsonValue(id));
		body.addChild("choice", new JsonValue(choice));
		post("/api/bridge/goal_choice", body, SHORT_TIMEOUT, new Listener() {
			@Override
			public void onResult(JsonValue result) {
				if (!runId.equals(activeRunId)) return;
				if (result == null) {
					if (choice.equals("title")) {
						activeRunId = null; //⑥(quit)을 보내지 않는다
						goToTitle();
					} else if (goalWindowId == id) {
						goalWindowId = id - 1;
					}
				} else if (!result.getBoolean("ok", false) && goalWindowId == id) {
					goalWindowId = id - 1;
				}
			}
		});
	}

	private static void goToTitle(){
		if (!(Game.scene() instanceof GameScene)) return;
		try {
			Dungeon.saveAll();
		} catch (IOException e) {
			ShatteredPixelDungeon.reportException(e);
		}
		Game.switchScene(TitleScene.class);
	}

	//⑤ 던전 도착: [AI로 시작]한 판의 첫 GameScene에서, 주인공이 조작을 기다릴 때 한 번만 보낸다
	private static void checkArrival(){
		Scene scene = Game.scene();
		if (scene != arrivalScene){
			arrivalScene = scene;
			arrivalTime = 0;
		}
		arrivalTime += Game.elapsed;
		if (arrivalTime < ARRIVE_DELAY || Dungeon.hero == null || !Dungeon.hero.ready
				|| InterlevelScene.mode != InterlevelScene.Mode.NONE) return;

		final String runId = pendingRunId;
		pendingRunId = null; //층을 옮겨 GameScene이 다시 만들어져도 다시 보내지 않는다
		if (Dungeon.depth != 1){
			notStarted();
			return;
		}
		JsonValue body = object();
		body.addChild("run_id", new JsonValue(runId));
		body.addChild("depth", new JsonValue(Dungeon.depth));
		body.addChild("seed_code", new JsonValue(DungeonSeed.convertToCode(Dungeon.seed)));
		post("/api/bridge/arrived", body, SHORT_TIMEOUT, new Listener() {
			@Override
			public void onResult(JsonValue result) {
				if (result != null && result.getBoolean("ok", false)) {
					resetState(); //⑧ 상태 번호와 비교 값을 새 판으로 (다음 프레임에 첫 상태 start를 보낸다)
					SPDSettings.aiGoalMark(GamesInProgress.curSlot, Dungeon.seed, ""); //이 슬롯의 지난 판 달성 표시를 지운다 (A-6-6)
					creditsRunId = null; //지난 판의 보이지 않은 크레딧은 버린다
					activeRunId = runId;
					sinceHeartbeat = HEARTBEAT_EVERY; //첫 신호를 바로 보낸다
					deathSent = false;
					heartbeatFails = 0;
				} else {
					notStarted();
				}
			}
		});
	}

	private static void notStarted(){
		GLog.w(Messages.get(GameScene.class, "ai_not_started"));
	}

	public interface Listener {
		//렌더 스레드에서 불린다. 응답이 JSON 객체가 아니면 body는 null
		void onResult( JsonValue body );
	}

	public static void get( String path, Listener listener ){
		send(Net.HttpMethods.GET, path, null, SHORT_TIMEOUT, listener);
	}

	public static void post( String path, JsonValue body, int timeout, Listener listener ){
		send(Net.HttpMethods.POST, path, body.toJson(JsonWriter.OutputType.json), timeout, listener);
	}

	//AI 관찰기를 새 명령 창에서 켠다: ai-bridge 폴더에서 python web.py --panels (Windows 전용)
	//게임을 실행한 폴더에서 위로 올라가며 ai-bridge/web.py를 찾는다. 못 찾거나 켜지 못하면 false
	public static boolean launchWatcher(){
		try {
			if (!System.getProperty("os.name", "").startsWith("Windows")) return false;
			File dir = findWatcherDir();
			if (dir == null) return false;
			//cmd /k: python이 오류로 끝나도 창이 남아서 오류 글을 볼 수 있다
			new ProcessBuilder("cmd", "/c", "start", "\"nokpixel-ai-watcher\"", "/D", dir.getAbsolutePath(),
					"cmd", "/k", "python", "web.py", "--panels")
					.directory(dir)
					.start();
			return true;
		} catch (Exception e) {
			return false;
		}
	}

	private static File findWatcherDir(){
		File dir = new File(System.getProperty("user.dir", ".")).getAbsoluteFile();
		while (dir != null) {
			File candidate = new File(dir, "ai-bridge");
			if (new File(candidate, "web.py").isFile()) return candidate;
			dir = dir.getParentFile();
		}
		return null;
	}

	public static JsonValue object(){
		return new JsonValue(JsonValue.ValueType.object);
	}

	private static void send( String method, String path, String content, int timeout, final Listener listener ){
		Net.HttpRequest request = new Net.HttpRequest(method);
		request.setUrl(HOST + path);
		//Python은 이 헤더와 JSON이 있는 요청만 받는다 (다른 웹사이트 요청 막기)
		request.setHeader("X-Nokpixel-Bridge", "1");
		request.setHeader("Content-Type", "application/json");
		request.setTimeOut(timeout);
		if (content != null) request.setContent(content);

		try {
			Gdx.net.sendHttpRequest(request, new Net.HttpResponseListener() {
				@Override
				public void handleHttpResponse( Net.HttpResponse httpResponse ) {
					JsonValue body = null;
					try {
						JsonValue value = new JsonReader().parse(httpResponse.getResultAsString());
						if (value != null && value.isObject()) body = value;
					} catch (Exception e) {
						body = null;
					}
					deliver(listener, body);
				}

				@Override
				public void failed( Throwable t ) {
					deliver(listener, null);
				}

				@Override
				public void cancelled() {
					deliver(listener, null);
				}
			});
		} catch (Exception e) {
			deliver(listener, null);
		}
	}

	private static void deliver( final Listener listener, final JsonValue body ){
		Game.runOnRenderThread(new Callback() {
			@Override
			public void call() {
				try {
					listener.onResult(body);
				} catch (Exception e) {
					//받는 쪽에서 난 오류도 게임을 끄지 않게 기록만 한다
					Game.reportException(e);
				}
			}
		});
	}
}
