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

import com.shatteredpixel.shatteredpixeldungeon.Challenges;
import com.shatteredpixel.shatteredpixeldungeon.Chrome;
import com.shatteredpixel.shatteredpixeldungeon.Dungeon;
import com.shatteredpixel.shatteredpixeldungeon.GamesInProgress;
import com.shatteredpixel.shatteredpixeldungeon.SPDSettings;
import com.shatteredpixel.shatteredpixeldungeon.ShatteredPixelDungeon;
import com.shatteredpixel.shatteredpixeldungeon.messages.Messages;
import com.shatteredpixel.shatteredpixeldungeon.sprites.CharSprite;
import com.shatteredpixel.shatteredpixeldungeon.ui.ActionIndicator;
import com.shatteredpixel.shatteredpixeldungeon.ui.RenderedTextBlock;
import com.shatteredpixel.shatteredpixeldungeon.ui.StyledButton;
import com.shatteredpixel.shatteredpixeldungeon.ui.TitleBackground;
import com.shatteredpixel.shatteredpixeldungeon.ui.Window;
import com.shatteredpixel.shatteredpixeldungeon.windows.WndTextInput;
import com.watabou.noosa.Camera;
import com.watabou.noosa.ColorBlock;
import com.watabou.noosa.Game;
import com.watabou.utils.RectF;

//[nokpixel-ai-watcher] 캐릭터 선택 뒤에 AI 판을 설정하는 장면 (docs/project/bridge.md 2장)
//지금은 화면과 값 기억만 있다. AI 관찰기(Python)와는 아직 연결하지 않아서 [AI 없이 시작]만 쓸 수 있다.
public class AISetupScene extends PixelScene {

	private static final int BTN_HEIGHT = 16;
	private static final int GAP = 2;
	private static final int SECTION_COLOR = 0xAAAAAA;

	private StyledButton btnGuide;
	private StyledButton btnMode;
	private StyledButton btnSteps;
	private StyledButton btnPlayer;
	private StyledButton btnStartAI;
	private ColorBlock[] liveFrame;
	private RenderedTextBlock notice;

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

		String model = SPDSettings.aiModel();
		StyledButton btnModel = button(Messages.get(this, "model", model.isEmpty() ? Messages.get(this, "model_none") : model), null);
		btnModel.enable(false); //모델 목록은 AI 관찰기에서 받아 온다 (다음 단계)
		pos = place(btnModel, left, pos, width);

		btnGuide = button("", new Runnable() {
			@Override
			public void run() {
				SPDSettings.aiGuide(!SPDSettings.aiGuide());
				refresh();
			}
		});
		pos = place(btnGuide, left, pos, width);

		RenderedTextBlock keyStatus = renderTextBlock(Messages.get(this, "key_status"), 6);
		keyStatus.maxWidth(width);
		keyStatus.setPos(left, pos + 1);
		align(keyStatus);
		add(keyStatus);
		pos = keyStatus.bottom() + 3;

		float half = (width - GAP) / 2f;
		StyledButton btnKey = button(Messages.get(this, "key_input"), new Runnable() {
			@Override
			public void run() {
				showKeyInput();
			}
		});
		btnKey.setRect(left, pos, half, BTN_HEIGHT);
		align(btnKey);
		StyledButton btnTest = button(Messages.get(this, "key_test"), null);
		btnTest.enable(false);
		btnTest.setRect(left + half + GAP, pos, half, BTN_HEIGHT);
		align(btnTest);
		pos += BTN_HEIGHT + 6;

		//묶음 2: 실험 옵션
		pos = section(Messages.get(this, "section_options"), left, pos, width);

		btnMode = button("", new Runnable() {
			@Override
			public void run() {
				SPDSettings.aiDryRun(!SPDSettings.aiDryRun());
				refresh();
			}
		});
		liveFrame = new ColorBlock[4];
		for (int i = 0; i < liveFrame.length; i++) {
			liveFrame[i] = new ColorBlock(1, 1, 0xFF000000 | CharSprite.NEGATIVE);
			add(liveFrame[i]);
		}
		pos = place(btnMode, left, pos, width);
		frame(btnMode);

		btnSteps = button("", new Runnable() {
			@Override
			public void run() {
				showStepsInput();
			}
		});
		pos = place(btnSteps, left, pos, width);

		StyledButton btnLessons = button(Messages.get(this, "lessons_none"), null);
		btnLessons.enable(false); //교훈 목록은 AI 관찰기에서 받아 온다 (다음 단계)
		pos = place(btnLessons, left, pos, width);

		btnPlayer = button("", new Runnable() {
			@Override
			public void run() {
				showPlayerInput();
			}
		});
		pos = place(btnPlayer, left, pos, width) + 6;

		//시작
		btnStartAI = button("", null);
		btnStartAI.textColor(Window.TITLE_COLOR);
		btnStartAI.enable(false); //AI 관찰기와 연결되고 키 연결 시험이 성공해야 눌린다 (다음 단계)
		pos = place(btnStartAI, left, pos, width);

		StyledButton btnStart = button(Messages.get(this, "start_without_ai"), new Runnable() {
			@Override
			public void run() {
				//HeroSelectScene의 원래 [시작] 순서를 그대로 옮겼다. 원작과 똑같이 동작해야 한다
				Dungeon.hero = null;
				Dungeon.daily = Dungeon.dailyReplay = false;
				Dungeon.initSeed();
				ActionIndicator.clearAction();
				InterlevelScene.mode = InterlevelScene.Mode.DESCEND;

				Game.switchScene( InterlevelScene.class );
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
		if (!SPDSettings.aiDryRun()) {
			notice(Messages.get(this, "last_was_live") + "\n" + Messages.get(this, "not_connected"));
		} else {
			notice(Messages.get(this, "not_connected"));
		}

		refresh();
		fadeIn();
	}

	private StyledButton button(String text, final Runnable action) {
		StyledButton btn = new StyledButton(Chrome.Type.GREY_BUTTON_TR, text, 6) {
			@Override
			protected void onClick() {
				super.onClick();
				//"지난번 판은 실제 조작" 안내는 처음 한 번만 보이고, 다른 버튼을 누르면 기본 안내로 돌아간다
				notice(Messages.get(AISetupScene.class, "not_connected"));
				if (action != null) action.run();
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

	//실제 조작일 때 판 방식 버튼 둘레에 그리는 빨간 테두리
	private void frame(StyledButton btn) {
		liveFrame[0].size(btn.width() + 2, 1);
		liveFrame[0].x = btn.left() - 1; liveFrame[0].y = btn.top() - 1;
		liveFrame[1].size(btn.width() + 2, 1);
		liveFrame[1].x = btn.left() - 1; liveFrame[1].y = btn.bottom();
		liveFrame[2].size(1, btn.height());
		liveFrame[2].x = btn.left() - 1; liveFrame[2].y = btn.top();
		liveFrame[3].size(1, btn.height());
		liveFrame[3].x = btn.right(); liveFrame[3].y = btn.top();
	}

	private void notice(String text) {
		notice.text(text);
	}

	//저장된 값으로 버튼 글자를 다시 쓴다
	private void refresh() {
		btnGuide.text(Messages.get(this, "guide", Messages.get(this, SPDSettings.aiGuide() ? "guide_on" : "guide_off")));

		boolean live = !SPDSettings.aiDryRun();
		btnMode.text(Messages.get(this, "mode", Messages.get(this, live ? "mode_live" : "mode_dry")));
		if (live) btnMode.textColor(CharSprite.NEGATIVE);
		else btnMode.textColor(0xFFFFFF);
		for (ColorBlock line : liveFrame) line.visible = live;
		btnStartAI.text(Messages.get(this, live ? "start_ai_live" : "start_ai"));
		btnStartAI.enable(false); //글자를 바꾸면 흐림이 풀려서 다시 건다

		btnSteps.text(Messages.get(this, "steps", SPDSettings.aiSteps()));
		btnPlayer.text(Messages.get(this, "player", SPDSettings.aiPlayer()));
	}

	//키는 가려서 받고, 확인을 누르면 바로 버린다. 어디에도 저장하지 않는다 (bridge.md 4장)
	private void showKeyInput() {
		ShatteredPixelDungeon.scene().addToFront(new WndTextInput(
				Messages.get(this, "key_title"),
				Messages.get(this, "key_desc"),
				"", 200, false,
				Messages.get(this, "key_ok"),
				Messages.get(this, "cancel")) {
			{
				textBox.setPasswordMode(true);
			}

			@Override
			public void onSelect(boolean positive, String text) {
				if (positive) notice(Messages.get(AISetupScene.class, "key_dropped"));
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
					notice(Messages.get(AISetupScene.class, "steps_invalid"));
					return;
				}
				SPDSettings.aiSteps(steps);
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
