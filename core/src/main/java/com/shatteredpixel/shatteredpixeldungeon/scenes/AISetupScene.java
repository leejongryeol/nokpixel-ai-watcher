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

package com.shatteredpixel.shatteredpixeldungeon.scenes;

import com.badlogic.gdx.utils.JsonValue;
import com.shatteredpixel.shatteredpixeldungeon.AIBridge;
import com.shatteredpixel.shatteredpixeldungeon.Challenges;
import com.shatteredpixel.shatteredpixeldungeon.Chrome;
import com.shatteredpixel.shatteredpixeldungeon.Dungeon;
import com.shatteredpixel.shatteredpixeldungeon.GamesInProgress;
import com.shatteredpixel.shatteredpixeldungeon.SPDSettings;
import com.shatteredpixel.shatteredpixeldungeon.ShatteredPixelDungeon;
import com.shatteredpixel.shatteredpixeldungeon.messages.Messages;
import com.shatteredpixel.shatteredpixeldungeon.ui.ActionIndicator;
import com.shatteredpixel.shatteredpixeldungeon.ui.RenderedTextBlock;
import com.shatteredpixel.shatteredpixeldungeon.ui.StyledButton;
import com.shatteredpixel.shatteredpixeldungeon.ui.TitleBackground;
import com.shatteredpixel.shatteredpixeldungeon.ui.Window;
import com.shatteredpixel.shatteredpixeldungeon.windows.WndOptions;
import com.shatteredpixel.shatteredpixeldungeon.windows.WndTextInput;
import com.watabou.noosa.Camera;
import com.watabou.noosa.ColorBlock;
import com.watabou.noosa.Game;
import com.watabou.utils.RectF;

//[nokpixel-ai-watcher] 캐릭터 선택 뒤에 AI 판을 설정하는 장면 (docs/project/bridge.md 2장)
//AI 관찰기(Python web.py)에 상태를 묻고, 키 보내기·연결 시험·판 준비를 한다 (bridge.md 3장 ①~④).
//관찰기가 꺼져 있으면 [AI 관찰기 켜기]로 이 컴퓨터에서 바로 켤 수 있다. AI 판은 언제나 실제 조작이다.
//[AI 없이 시작]과 [뒤로]는 Python과 관계없이 언제나 원작과 같이 동작한다.
public class AISetupScene extends PixelScene {

	private static final int BTN_HEIGHT = 16;
	private static final int GAP = 2;
	private static final int SECTION_COLOR = 0xAAAAAA;
	private static final float STATUS_EVERY = 3f; //장면에 있는 동안 상태 조회 간격(초)
	private static final int LESSONS_MAX = 8; //교훈 고르기 창에 보여 줄 최근 판 수
	private static final float LAUNCH_WAIT = 20f; //[AI 관찰기 켜기] 뒤 연결을 기다리는 최대 시간(초)

	private StyledButton btnModel;
	private StyledButton btnGuide;
	private RenderedTextBlock keyStatus;
	private StyledButton btnKey;
	private StyledButton btnTest;
	private StyledButton btnSteps;
	private StyledButton btnLessons;
	private StyledButton btnPlayer;
	private StyledButton btnStartAI;
	private RenderedTextBlock notice;

	//AI 관찰기와 주고받은 상태
	private JsonValue status; //마지막으로 받은 ① 응답. 못 받으면 null
	private boolean everConnected; //한 번이라도 연결됐으면 "끊김" 안내를 쓴다
	private boolean checking = true; //장면을 열고 첫 ① 응답을 기다리는 중
	private boolean statusInFlight;
	private float sinceStatus;
	private boolean testing;
	private String testReason; //고른 모델 회사의 마지막 ③ 결과 (성공이면 null)
	private boolean sendingKey;
	private boolean starting;
	private float launching; //[AI 관찰기 켜기]를 누른 뒤 남은 기다림(초). 0이면 켜는 중이 아님
	private boolean runFailed;
	private String flash; //한 번만 보이는 안내. 버튼을 하나 누르면 지운다
	private boolean destroyed;

	@Override
	public void create() {
		super.create();

		int w = Camera.main.width;
		int h = Camera.main.height;
		RectF insets = getCommonInsets();

		add(new TitleBackground(w, h));

		w -= insets.right + insets.left;
		h -= insets.top + insets.bottom;

		int width = Math.min(w - 8, 172);
		float left = insets.left + (w - width) / 2f;
		float pos = insets.top + 4;

		RenderedTextBlock title = renderTextBlock(Messages.get(this, "title"), 9);
		title.hardlight(Window.TITLE_COLOR);
		title.setPos(insets.left + (w - title.width()) / 2f, pos);
		align(title);
		add(title);
		pos = title.bottom() + 4;

		//캐릭터 선택에서 정한 값 (읽기 전용)
		String hero = GamesInProgress.selectedClass != null ? GamesInProgress.selectedClass.title() : "-";
		String seed = SPDSettings.customSeed().isEmpty() ? Messages.get(this, "seed_random") : SPDSettings.customSeed();
		RenderedTextBlock run = renderTextBlock(Messages.get(this, "run_info", hero,
				Challenges.activeChallenges(SPDSettings.challenges()), seed), 6);
		run.maxWidth(width);
		run.setPos(insets.left + (w - run.width()) / 2f, pos);
		align(run);
		add(run);
		pos = run.bottom() + 6;

		//묶음 1: 매번 보는 것
		pos = section(Messages.get(this, "section_always"), left, pos, width);

		btnModel = button("", new Runnable() {
			@Override
			public void run() {
				showModelChooser();
			}
		});
		pos = place(btnModel, left, pos, width);

		btnGuide = button("", new Runnable() {
			@Override
			public void run() {
				SPDSettings.aiGuide(!SPDSettings.aiGuide());
			}
		});
		pos = place(btnGuide, left, pos, width);

		//키 상태는 두 줄까지 들어가게 자리를 잡아 둔다
		keyStatus = renderTextBlock(6);
		keyStatus.maxWidth(width);
		keyStatus.setPos(left, pos + 1);
		add(keyStatus);
		pos += 17;

		float half = (width - GAP) / 2f;
		btnKey = button(Messages.get(this, "key_input"), new Runnable() {
			@Override
			public void run() {
				showKeyInput();
			}
		});
		btnKey.setRect(left, pos, half, BTN_HEIGHT);
		align(btnKey);
		btnTest = button("", new Runnable() {
			@Override
			public void run() {
				if (!connected()) {
					launchWatcher();
				} else if (status.getBoolean("running", false)) {
					requestStatus(); //[관찰기 다시 확인]
				} else {
					testKey();
				}
			}
		});
		btnTest.setRect(left + half + GAP, pos, half, BTN_HEIGHT);
		align(btnTest);
		pos += BTN_HEIGHT + 6;

		//묶음 2: 실험 옵션
		pos = section(Messages.get(this, "section_options"), left, pos, width);

		btnSteps = button("", new Runnable() {
			@Override
			public void run() {
				showStepsInput();
			}
		});
		pos = place(btnSteps, left, pos, width);

		btnLessons = button("", new Runnable() {
			@Override
			public void run() {
				showLessonsChooser();
			}
		});
		pos = place(btnLessons, left, pos, width);

		btnPlayer = button("", new Runnable() {
			@Override
			public void run() {
				showPlayerInput();
			}
		});
		pos = place(btnPlayer, left, pos, width) + 6;

		//시작
		btnStartAI = button("", new Runnable() {
			@Override
			public void run() {
				startWithAI();
			}
		});
		btnStartAI.textColor(Window.TITLE_COLOR);
		pos = place(btnStartAI, left, pos, width);

		StyledButton btnStart = button(Messages.get(this, "start_without_ai"), new Runnable() {
			@Override
			public void run() {
				AIBridge.pendingRunId = null; //AI 없이 시작한 판에서는 던전 도착 알림을 보내지 않는다
				startGame();
			}
		});
		btnStart.setRect(left, pos, width - 40 - GAP, BTN_HEIGHT);
		align(btnStart);
		StyledButton btnBack = button(Messages.get(this, "back"), new Runnable() {
			@Override
			public void run() {
				onBackPressed();
			}
		});
		btnBack.setRect(left + width - 40, pos, 40, BTN_HEIGHT);
		align(btnBack);
		pos += BTN_HEIGHT + 6;

		notice = renderTextBlock(6);
		notice.maxWidth(width);
		notice.setPos(left, pos);
		add(notice);
		refresh();
		requestStatus();
		fadeIn();
	}

	@Override
	public void update() {
		super.update();
		//장면에 있는 동안만 3초마다 묻는다. 장면을 떠나면 update가 불리지 않아 저절로 멈춘다
		if (!statusInFlight) {
			sinceStatus += Game.elapsed;
			if (sinceStatus >= STATUS_EVERY) requestStatus();
		}
		if (launching > 0) {
			launching -= Game.elapsed;
			if (launching <= 0) {
				launching = 0;
				if (!connected()) flash = Messages.get(this, "launch_timeout");
				refresh();
			}
		}
	}

	@Override
	public void destroy() {
		destroyed = true; //장면을 떠난 뒤에 온 응답은 버린다
		super.destroy();
	}

	private StyledButton button(String text, final Runnable action) {
		StyledButton btn = new StyledButton(Chrome.Type.GREY_BUTTON_TR, text, 6) {
			@Override
			protected void onClick() {
				super.onClick();
				flash = null;
				if (action != null) action.run();
				refresh();
			}
		};
		add(btn);
		return btn;
	}

	private float place(StyledButton btn, float left, float pos, float width) {
		btn.setRect(left, pos, width, BTN_HEIGHT);
		align(btn);
		return pos + BTN_HEIGHT + GAP;
	}

	private float section(String text, float left, float pos, float width) {
		RenderedTextBlock label = renderTextBlock(text, 6);
		label.hardlight(SECTION_COLOR);
		label.setPos(left, pos);
		align(label);
		add(label);
		ColorBlock line = new ColorBlock(width, 1, 0xFF000000 | SECTION_COLOR);
		line.x = left;
		line.y = label.bottom() + 1;
		line.alpha(0.5f);
		add(line);
		return line.y + 3;
	}

	// ---------------- AI 관찰기와 주고받기 ----------------

	private boolean connected() {
		return status != null;
	}

	//① 상태 조회
	private void requestStatus() {
		if (statusInFlight) return;
		statusInFlight = true;
		sinceStatus = 0;
		AIBridge.get("/api/bridge/status", new AIBridge.Listener() {
			@Override
			public void onResult(JsonValue body) {
				statusInFlight = false;
				sinceStatus = 0;
				if (destroyed) return;
				checking = false;
				status = body != null && body.has("models") && body.get("models").size > 0 ? body : null;
				if (status != null) {
					everConnected = true;
					launching = 0;
					fixChoices();
					JsonValue key = key();
					if (key != null && key.getBoolean("tested_ok", false)) testReason = null;
				}
				refresh();
			}
		});
	}

	//② 키 보내기. 입력한 글자는 보낸 뒤 바로 버리고, 게임 어디에도 저장하지 않는다 (bridge.md 4장)
	private void sendKey(String key) {
		JsonValue body = AIBridge.object();
		body.addChild("provider", new JsonValue(provider()));
		body.addChild("key", new JsonValue(key));
		sendingKey = true;
		AIBridge.post("/api/bridge/key", body, AIBridge.SHORT_TIMEOUT, new AIBridge.Listener() {
			@Override
			public void onResult(JsonValue result) {
				sendingKey = false;
				if (destroyed) return;
				if (result != null && result.getBoolean("ok", false)) {
					testReason = null;
					flash = Messages.get(AISetupScene.class, "key_saved", result.getString("last4", ""));
				} else if (result != null && "bad_key".equals(result.getString("reason", ""))) {
					flash = Messages.get(AISetupScene.class, "key_bad");
				} else {
					flash = Messages.get(AISetupScene.class, "key_send_failed");
				}
				requestStatus();
				refresh();
			}
		});
	}

	//③ 연결 시험
	private void testKey() {
		JsonValue body = AIBridge.object();
		body.addChild("model", new JsonValue(SPDSettings.aiModel()));
		testing = true;
		testReason = null;
		AIBridge.post("/api/bridge/test", body, AIBridge.TEST_TIMEOUT, new AIBridge.Listener() {
			@Override
			public void onResult(JsonValue result) {
				testing = false;
				if (destroyed) return;
				String reason = result != null ? result.getString("reason", "other") : "other";
				testReason = "ok".equals(reason) ? null : reason;
				requestStatus();
				refresh();
			}
		});
	}

	//AI 관찰기(web.py)를 이 컴퓨터에서 켠다. 켜지면 3초마다 하는 ①이 저절로 이어 준다
	private void launchWatcher() {
		if (launching > 0) return;
		if (AIBridge.launchWatcher()) {
			launching = LAUNCH_WAIT;
		} else {
			flash = Messages.get(this, "launch_failed");
		}
	}

	//④ 판 설정 확정. 성공하면 원래 시작 순서로 던전에 들어간다. 실패하면 장면에 머문다
	private void startWithAI() {
		if (!canStartAI()) return;
		JsonValue body = AIBridge.object();
		body.addChild("player", new JsonValue(SPDSettings.aiPlayer()));
		body.addChild("model", new JsonValue(SPDSettings.aiModel()));
		body.addChild("guide", new JsonValue(SPDSettings.aiGuide()));
		body.addChild("dry_run", new JsonValue(false)); //게임에서 시작하는 AI 판은 언제나 실제 조작 (생각만 하기는 mvp.py --dry-run)
		body.addChild("steps", new JsonValue(SPDSettings.aiSteps()));
		body.addChild("lessons_from", new JsonValue(SPDSettings.aiLessonsFrom()));
		body.addChild("hero_class", new JsonValue(GamesInProgress.selectedClass != null ? GamesInProgress.selectedClass.name() : ""));
		//AI 입력의 [이번 판]에 쓰는 이름: 게임 화면에 보이는 언어 그대로
		body.addChild("hero_title", new JsonValue(GamesInProgress.selectedClass != null ? GamesInProgress.selectedClass.title() : ""));
		int challenges = SPDSettings.challenges();
		body.addChild("challenges", new JsonValue(challenges));
		JsonValue names = new JsonValue(JsonValue.ValueType.array);
		JsonValue titles = new JsonValue(JsonValue.ValueType.array);
		for (int i = 0; i < Challenges.MASKS.length; i++) {
			if ((challenges & Challenges.MASKS[i]) != 0) {
				names.addChild(new JsonValue(Challenges.NAME_IDS[i]));
				titles.addChild(new JsonValue(Messages.get(Challenges.class, Challenges.NAME_IDS[i])));
			}
		}
		body.addChild("challenge_names", names);
		body.addChild("challenge_titles", titles);
		body.addChild("custom_seed", new JsonValue(SPDSettings.customSeed()));

		starting = true;
		runFailed = false;
		AIBridge.post("/api/bridge/run", body, AIBridge.SHORT_TIMEOUT, new AIBridge.Listener() {
			@Override
			public void onResult(JsonValue result) {
				starting = false;
				if (destroyed) return;
				if (result != null && result.getBoolean("ok", false)) {
					//이 판의 첫 던전 도착에서 Python에 알리고(⑤) AI가 시작한다
					AIBridge.pendingRunId = result.getString("run_id", null);
					startGame();
					return;
				}
				runFailed = true;
				requestStatus(); //다른 판이 진행 중이면 그 안내로 바뀐다
				refresh();
			}
		});
	}

	//HeroSelectScene의 원래 [시작] 순서를 그대로 옮겼다. 원작과 똑같이 동작해야 한다
	private void startGame() {
		Dungeon.hero = null;
		Dungeon.daily = Dungeon.dailyReplay = false;
		Dungeon.initSeed();
		ActionIndicator.clearAction();
		InterlevelScene.mode = InterlevelScene.Mode.DESCEND;

		Game.switchScene( InterlevelScene.class );
	}

	// ---------------- 받은 상태 읽기 ----------------

	private JsonValue findModel(String id) {
		if (!connected()) return null;
		for (JsonValue m = status.get("models").child; m != null; m = m.next) {
			if (id.equals(m.getString("id", ""))) return m;
		}
		return null;
	}

	//지난 값이 목록에 없으면 첫 모델, 교훈은 "없음"으로 바꾼다
	private void fixChoices() {
		if (findModel(SPDSettings.aiModel()) == null) {
			SPDSettings.aiModel(status.get("models").child.getString("id", ""));
			testReason = null;
		}
		String lessons = SPDSettings.aiLessonsFrom();
		if (!lessons.isEmpty() && lessonLabel(lessons) == null) SPDSettings.aiLessonsFrom("");
	}

	private String provider() {
		JsonValue m = findModel(SPDSettings.aiModel());
		return m != null ? m.getString("provider", "") : "";
	}

	private String providerName() {
		JsonValue names = connected() ? status.get("providers") : null;
		return names != null ? names.getString(provider(), provider()) : provider();
	}

	private JsonValue key() {
		JsonValue keys = connected() ? status.get("keys") : null;
		return keys != null ? keys.get(provider()) : null;
	}

	private String lessonLabel(String runId) {
		JsonValue sources = connected() ? status.get("lesson_sources") : null;
		if (sources == null) return null;
		for (JsonValue s = sources.child; s != null; s = s.next) {
			if (runId.equals(s.getString("run_id", ""))) return s.getString("label", runId);
		}
		return null;
	}

	private boolean canStartAI() {
		JsonValue key = key();
		//첫 판 튜토리얼은 화면과 던전이 달라서 AI로 시작하지 않는다 (bridge.md 9장 A-5-4)
		return !SPDSettings.intro() && connected() && !status.getBoolean("running", false) && key != null
				&& key.getBoolean("tested_ok", false) && !testing && !starting;
	}

	// ---------------- 화면 ----------------

	//저장된 값과 받은 상태로 버튼 글자·눌림·안내를 다시 쓴다
	private void refresh() {
		boolean online = connected();
		boolean running = online && status.getBoolean("running", false);

		JsonValue model = findModel(SPDSettings.aiModel());
		String modelText = model != null ? model.getString("name", SPDSettings.aiModel())
				: SPDSettings.aiModel().isEmpty() ? Messages.get(this, "model_none") : SPDSettings.aiModel();
		btnModel.text(Messages.get(this, "model", modelText));
		btnModel.enable(online && !testing && !starting);

		btnGuide.text(Messages.get(this, "guide", Messages.get(this, SPDSettings.aiGuide() ? "guide_on" : "guide_off")));

		keyStatus.text(keyLine());
		btnKey.enable(online && !sendingKey && !testing && !starting);

		//[연결 시험], [AI 관찰기 켜기], [관찰기 다시 확인]은 같은 자리를 쓰므로 글자와 색을 분명히 다르게 한다
		if (testing) {
			btnTest.text(Messages.get(this, "testing_btn"));
			btnTest.textColor(0xFFFFFF);
			btnTest.enable(false);
		} else if (!online) {
			btnTest.text(Messages.get(this, launching > 0 ? "launching_btn" : "launch"));
			btnTest.textColor(Window.TITLE_COLOR);
			btnTest.enable(launching <= 0);
		} else if (running) {
			btnTest.text(Messages.get(this, "recheck"));
			btnTest.textColor(Window.TITLE_COLOR);
			btnTest.enable(true);
		} else {
			btnTest.text(Messages.get(this, "key_test"));
			btnTest.textColor(0xFFFFFF);
			JsonValue key = key();
			btnTest.enable(key != null && key.getBoolean("present", false) && !starting);
		}

		btnSteps.text(Messages.get(this, "steps", SPDSettings.aiSteps()));

		String lessons = SPDSettings.aiLessonsFrom();
		String label = lessons.isEmpty() ? null : lessonLabel(lessons);
		btnLessons.text(Messages.get(this, "lessons", label != null ? label : Messages.get(this, "lessons_item_none")));
		btnLessons.enable(online && status.has("lesson_sources") && status.get("lesson_sources").size > 0);

		btnPlayer.text(Messages.get(this, "player", SPDSettings.aiPlayer()));

		btnStartAI.text(Messages.get(this, "start_ai"));
		btnStartAI.enable(canStartAI()); //글자를 바꾸면 흐림이 풀려서 마지막에 건다

		notice.text(noticeText());
	}

	private String keyLine() {
		if (!connected()) return Messages.get(this, "key_status");
		JsonValue key = key();
		if (key == null || !key.getBoolean("present", false)) return Messages.get(this, "key_line_none", providerName());
		String last4 = key.getString("last4", "");
		String at = key.getString("tested_at", "");
		String time = at.length() >= 16 ? at.substring(11, 16) : at; //"2026-11-02T14:03:11" → "14:03"
		if (key.getBoolean("tested_ok", false)) return Messages.get(this, "key_line_ok", providerName(), last4, time);
		if (!at.isEmpty()) return Messages.get(this, "key_line_fail", providerName(), last4, time);
		return Messages.get(this, "key_line_untested", providerName(), last4);
	}

	//안내 문구 (bridge.md 5장). 무엇을 하면 되는지 말한다
	private String noticeText() {
		if (flash != null) return flash;
		if (starting) return Messages.get(this, "preparing");
		if (!connected()) {
			if (checking) return Messages.get(this, "checking");
			if (launching > 0) return Messages.get(this, "launching");
			return Messages.get(this, everConnected ? "disconnected" : "python_off");
		}
		if (status.getBoolean("running", false)) return Messages.get(this, "other_run");
		if (runFailed) return Messages.get(this, "run_failed");
		if (testing) return Messages.get(this, "testing");
		JsonValue key = key();
		if (key == null || !key.getBoolean("present", false)) return Messages.get(this, "no_key", providerName());
		if (testReason != null) {
			switch (testReason) {
				case "key_invalid": case "no_key": return Messages.get(this, "key_invalid");
				case "no_credit": return Messages.get(this, "no_credit");
				case "model_unavailable":
					JsonValue model = findModel(SPDSettings.aiModel());
					return Messages.get(this, "model_unavailable", model != null ? model.getString("name", "") : SPDSettings.aiModel());
				case "timeout": return Messages.get(this, "timeout");
				default: return Messages.get(this, "test_other");
			}
		}
		if (SPDSettings.intro()) return Messages.get(this, "tutorial_first");
		if (key.getBoolean("tested_ok", false)) return Messages.get(this, "ready");
		return Messages.get(this, "need_test");
	}

	// ---------------- 입력 창 ----------------

	private void showModelChooser() {
		if (!connected()) return;
		final JsonValue models = status.get("models");
		String[] names = new String[models.size];
		int i = 0;
		for (JsonValue m = models.child; m != null; m = m.next) names[i++] = m.getString("name", "");
		ShatteredPixelDungeon.scene().addToFront(new WndOptions(Messages.get(this, "model_title"), "", names) {
			@Override
			protected void onSelect(int index) {
				String before = provider();
				SPDSettings.aiModel(models.get(index).getString("id", ""));
				if (!before.equals(provider())) testReason = null; //회사가 바뀌면 [AI로 시작]을 다시 판단한다
				runFailed = false;
				refresh();
			}
		});
	}

	private void showLessonsChooser() {
		if (!connected() || !status.has("lesson_sources")) return;
		JsonValue sources = status.get("lesson_sources");
		final int count = Math.min(sources.size, LESSONS_MAX);
		final String[] ids = new String[count + 1];
		String[] labels = new String[count + 1];
		ids[0] = "";
		labels[0] = Messages.get(this, "lessons_item_none");
		for (int i = 0; i < count; i++) {
			ids[i + 1] = sources.get(i).getString("run_id", "");
			labels[i + 1] = sources.get(i).getString("label", ids[i + 1]);
		}
		ShatteredPixelDungeon.scene().addToFront(new WndOptions(Messages.get(this, "lessons_title"), "", labels) {
			@Override
			protected void onSelect(int index) {
				SPDSettings.aiLessonsFrom(ids[index]);
				refresh();
			}
		});
	}

	//키는 가려서 받고, 확인을 누르면 AI 관찰기로 보낸 뒤 버린다. 입력 창에 이전 키를 채워 두지 않는다
	private void showKeyInput() {
		if (!connected() || provider().isEmpty()) return;
		ShatteredPixelDungeon.scene().addToFront(new WndTextInput(
				Messages.get(this, "key_title", providerName()),
				Messages.get(this, "key_desc"),
				"", 200, false,
				Messages.get(this, "key_ok"),
				Messages.get(this, "cancel")) {
			{
				textBox.setPasswordMode(true);
			}

			@Override
			public void onSelect(boolean positive, String text) {
				if (!positive || text.trim().isEmpty()) return;
				sendKey(text.trim());
				refresh();
			}
		});
	}

	private void showStepsInput() {
		ShatteredPixelDungeon.scene().addToFront(new WndTextInput(
				Messages.get(this, "steps_title"),
				Messages.get(this, "steps_desc"),
				Integer.toString(SPDSettings.aiSteps()), 3, false,
				Messages.get(this, "ok"),
				Messages.get(this, "cancel")) {
			@Override
			public void onSelect(boolean positive, String text) {
				if (!positive) return;
				int steps;
				try {
					steps = Integer.parseInt(text.trim());
				} catch (NumberFormatException e) {
					steps = 0;
				}
				if (steps < 1 || steps > 500) {
					flash = Messages.get(AISetupScene.class, "steps_invalid");
				} else {
					SPDSettings.aiSteps(steps);
				}
				refresh();
			}
		});
	}

	private void showPlayerInput() {
		ShatteredPixelDungeon.scene().addToFront(new WndTextInput(
				Messages.get(this, "player_title"),
				Messages.get(this, "player_desc"),
				SPDSettings.aiPlayer(), 16, false,
				Messages.get(this, "ok"),
				Messages.get(this, "cancel")) {
			@Override
			public void onSelect(boolean positive, String text) {
				if (!positive) return;
				text = text.trim();
				SPDSettings.aiPlayer(text.isEmpty() ? "player" : text);
				refresh();
			}
		});
	}

	@Override
	protected void onBackPressed() {
		ShatteredPixelDungeon.switchScene( HeroSelectScene.class );
	}
}
