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

package com.shatteredpixel.shatteredpixeldungeon.windows;

import com.shatteredpixel.shatteredpixeldungeon.AIBridge;
import com.shatteredpixel.shatteredpixeldungeon.messages.Messages;

//[nokpixel-ai-watcher] 최종 목표 달성 창 (A-6-6). 단계 0·1·2를 이뤘을 때 던전 화면 위에 띄운다.
//다른 장면으로 넘어가면 AI 판이 끝나므로 창으로 만든다. 떠 있는 동안 AI는 판단·키·명령을 보내지 않는다 (Python이 기다림).
//사람이 [다음 목표로] 또는 [타이틀로]를 골라야 닫힌다. ESC·바깥 클릭으로는 닫히지 않는다
public class WndAIGoal extends WndOptions {

	private final int id;

	public WndAIGoal( int id, String reached, int step, String next ){
		super(Messages.get(WndAIGoal.class, "title"),
				Messages.get(WndAIGoal.class, "body", reached, step, next),
				Messages.get(WndAIGoal.class, "next"),
				Messages.get(WndAIGoal.class, "to_title"));
		this.id = id;
	}

	@Override
	protected void onSelect( int index ){
		AIBridge.goalChoice(id, index == 0 ? "next" : "title");
	}

	@Override
	public void onBackPressed(){
		//고르기 전에는 닫지 않는다
	}
}
