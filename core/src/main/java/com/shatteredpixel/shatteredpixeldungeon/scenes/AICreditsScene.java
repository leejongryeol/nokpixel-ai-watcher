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
import com.shatteredpixel.shatteredpixeldungeon.ShatteredPixelDungeon;
import com.shatteredpixel.shatteredpixeldungeon.messages.Messages;
import com.shatteredpixel.shatteredpixeldungeon.ui.RedButton;
import com.shatteredpixel.shatteredpixeldungeon.ui.RenderedTextBlock;
import com.watabou.noosa.Camera;
import com.watabou.noosa.Game;

import java.util.Locale;

//[nokpixel-ai-watcher] 엔딩 크레딧 (A-6-6). 마지막 최종 목표(엔딩)를 이룬 AI 판에서, 원작 승리 흐름(아뮬렛 화면 [던전을 나간다]) 뒤에 보인다.
//글이 아래에서 위로 천천히 올라가고, 다 올라가거나 [타이틀로]·ESC를 누르면 타이틀로 간다.
//그 판의 기록은 AI 관찰기(⑪ /api/bridge/credits)에서 받는다. 못 받으면 기록 칸 없이 보인다
public class AICreditsScene extends PixelScene {

	private static final float SPEED = 10f; //올라가는 속도 (화면 점/초)
	private static final int TEXT_SIZE = 7;

	private RenderedTextBlock text;
	private float offset; //글 맨 위가 화면 맨 아래에서 올라간 거리
	private boolean leaving;

	@Override
	public void create() {
		super.create();

		text = PixelScene.renderTextBlock(TEXT_SIZE);
		text.align(RenderedTextBlock.CENTER_ALIGN);
		add(text);
		show(Messages.get(this, "loading"));

		RedButton btnTitle = new RedButton(Messages.get(this, "to_title")) {
			@Override
			protected void onClick() {
				toTitle();
			}
		};
		btnTitle.setRect(Camera.main.width - 62, Camera.main.height - 20, 60, 18);
		add(btnTitle);

		final String runId = AIBridge.takeCreditsRunId();
		if (runId != null) {
			AIBridge.get("/api/bridge/credits?run_id=" + runId, new AIBridge.Listener() {
				@Override
				public void onResult(JsonValue body) {
					if (!leaving) show(body != null && body.getBoolean("ok", false) ? record(body) : Messages.get(AICreditsScene.this, "no_record"));
				}
			});
		} else {
			show(Messages.get(this, "no_record"));
		}

		fadeIn();
	}

	//기록 칸 + 이 프로젝트 + 원작
	private void show( String record ){
		text.text(Messages.get(this, "head") + "\n\n" + record + "\n\n" + Messages.get(this, "project") + "\n\n" + Messages.get(this, "original"),
				Camera.main.width - 20);
		place();
	}

	private String record( JsonValue b ){
		StringBuilder goals = new StringBuilder();
		JsonValue list = b.get("goals");
		if (list != null) {
			for (JsonValue g = list.child; g != null; g = g.next) {
				goals.append("\n").append(Messages.get(this, "goal_line", g.getString("name", "?"), g.getInt("step", 0)));
			}
		}
		long seconds = b.getLong("seconds", 0);
		return Messages.get(this, "record",
				b.getString("model_name", "?"),
				b.getInt("steps", 0),
				String.format(Locale.ROOT, "%.2f", b.getFloat("cost_usd", 0)),
				b.getInt("hints", 0), b.getInt("pauses", 0),
				Messages.get(this, "time_hm", seconds / 3600, (seconds % 3600) / 60),
				b.getInt("points", 0), b.getInt("points_max", 0))
				+ goals;
	}

	private void place(){
		text.setPos((Camera.main.width - text.width()) / 2f, Camera.main.height - offset);
		align(text);
	}

	@Override
	public void update() {
		super.update();
		if (leaving) return;
		offset += SPEED * Game.elapsed;
		place();
		if (text.bottom() < 0) toTitle();
	}

	@Override
	protected void onBackPressed() {
		toTitle();
	}

	private void toTitle(){
		if (leaving) return;
		leaving = true;
		ShatteredPixelDungeon.switchNoFade(TitleScene.class);
	}
}
