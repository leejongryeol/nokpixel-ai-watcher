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
import com.badlogic.gdx.Net;
import com.badlogic.gdx.utils.JsonReader;
import com.badlogic.gdx.utils.JsonValue;
import com.badlogic.gdx.utils.JsonWriter;
import com.shatteredpixel.shatteredpixeldungeon.actors.Char;
import com.shatteredpixel.shatteredpixeldungeon.actors.hero.Hero;
import com.shatteredpixel.shatteredpixeldungeon.actors.mobs.Goo;
import com.shatteredpixel.shatteredpixeldungeon.actors.mobs.Mimic;
import com.shatteredpixel.shatteredpixeldungeon.actors.mobs.Mob;
import com.shatteredpixel.shatteredpixeldungeon.items.Item;
import com.shatteredpixel.shatteredpixeldungeon.items.potions.Potion;
import com.shatteredpixel.shatteredpixeldungeon.items.rings.Ring;
import com.shatteredpixel.shatteredpixeldungeon.items.scrolls.Scroll;
import com.shatteredpixel.shatteredpixeldungeon.messages.Messages;
import com.shatteredpixel.shatteredpixeldungeon.scenes.GameScene;
import com.shatteredpixel.shatteredpixeldungeon.scenes.InterlevelScene;
import com.shatteredpixel.shatteredpixeldungeon.utils.DungeonSeed;
import com.shatteredpixel.shatteredpixeldungeon.utils.GLog;
import com.watabou.noosa.Game;
import com.watabou.noosa.Scene;
import com.watabou.utils.Callback;
import com.watabou.utils.Signal;

import java.io.File;
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
				checkWaiting();
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
		synchronized (logLines) { logLines.clear(); }
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
		boolean waiting = hero != null && hero.isAlive() && hero.ready && Dungeon.level != null
				&& InterlevelScene.mode == InterlevelScene.Mode.NONE;
		if (waiting && !wasWaiting) sendState();
		wasWaiting = waiting;
	}

	private static void sendState(){
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
		if (prevDepth < 0) {
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
		body.addChild("last_command", new JsonValue(JsonValue.ValueType.nullValue)); //명령은 A-6-3에서
		body.addChild("ai", ai);
		body.addChild("record", record(hero));
		post("/api/bridge/state", body, SHORT_TIMEOUT, new Listener() {
			@Override
			public void onResult(JsonValue result) {
				//실패하면 버린다. 다음 대기 때 새 상태를 보낸다. want_command는 A-6-3부터 쓴다
			}
		});
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
	public static void onLeaveGame(){
		if (InterlevelScene.mode != InterlevelScene.Mode.NONE) return;
		pendingRunId = null;
		end(Statistics.gameWon ? "won" : "quit");
	}

	private static void end(String reason){
		if (activeRunId == null) return;
		JsonValue body = object();
		body.addChild("run_id", new JsonValue(activeRunId));
		body.addChild("reason", new JsonValue(reason));
		body.addChild("depth", new JsonValue(Dungeon.depth));
		activeRunId = null; //판이 끝났으므로 신호도 멈춘다. 닿지 않아도 신호가 끊겨서 Python은 키를 보내지 않는다
		post("/api/bridge/ended", body, SHORT_TIMEOUT, new Listener() {
			@Override
			public void onResult(JsonValue result) {
				//결과와 관계없이 게임은 그대로 진행한다
			}
		});
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
					if (!result.getBoolean("ok", false)) activeRunId = null;
				}
			}
		});
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
