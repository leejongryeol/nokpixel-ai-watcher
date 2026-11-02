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

import com.badlogic.gdx.utils.JsonValue;
import com.shatteredpixel.shatteredpixeldungeon.AIBridge;
import com.shatteredpixel.shatteredpixeldungeon.Dungeon;
import com.shatteredpixel.shatteredpixeldungeon.GamesInProgress;
import com.shatteredpixel.shatteredpixeldungeon.SPDSettings;
import com.shatteredpixel.shatteredpixeldungeon.ShatteredPixelDungeon;
import com.shatteredpixel.shatteredpixeldungeon.messages.Messages;
import com.shatteredpixel.shatteredpixeldungeon.scenes.GameScene;
import com.shatteredpixel.shatteredpixeldungeon.scenes.HeroSelectScene;
import com.shatteredpixel.shatteredpixeldungeon.scenes.InterlevelScene;
import com.shatteredpixel.shatteredpixeldungeon.scenes.RankingsScene;
import com.shatteredpixel.shatteredpixeldungeon.scenes.TitleScene;
import com.shatteredpixel.shatteredpixeldungeon.ui.Icons;
import com.shatteredpixel.shatteredpixeldungeon.ui.RedButton;
import com.shatteredpixel.shatteredpixeldungeon.ui.Window;
import com.watabou.noosa.Game;

import java.io.IOException;

public class WndGame extends Window {

	private static final int WIDTH		= 120;
	private static final int BTN_HEIGHT	= 20;
	private static final int GAP		= 2;
	
	private int pos;
	private boolean closed; //[nokpixel-ai-watcher] 창이 닫힌 뒤 온 관찰기 응답은 버린다
	
	public WndGame() {
		
		super();

		//settings
		RedButton curBtn;
		addButton( curBtn = new RedButton( Messages.get(this, "settings") ) {
			@Override
			protected void onClick() {
				hide();
				GameScene.show(new WndSettings());
			}
		});
		curBtn.icon(Icons.get(Icons.PREFS));

		//[nokpixel-ai-watcher] AI 관찰기 켜기: 꺼져 있으면 켜기만 한다. AI 판은 시작하지 않는다
		addButton( curBtn = new RedButton( Messages.get(this, "watcher") ) {
			@Override
			protected void onClick() {
				final RedButton btn = this;
				btn.text(Messages.get(WndGame.class, "watcher_checking"));
				btn.enable(false);
				AIBridge.get("/api/bridge/status", new AIBridge.Listener() {
					@Override
					public void onResult(JsonValue body) {
						if (closed) return;
						if (body != null && body.has("models")) {
							btn.text(Messages.get(WndGame.class, "watcher_on"));
							btn.enable(false); //글자를 바꾸면 흐림이 풀려서 다시 건다
						} else if (AIBridge.launchWatcher()) {
							btn.text(Messages.get(WndGame.class, "watcher_launching"));
							btn.enable(false);
						} else {
							btn.text(Messages.get(WndGame.class, "watcher_failed"));
							btn.enable(true);
						}
					}
				});
			}
		});
		curBtn.textColor(Window.TITLE_COLOR);

		// Challenges window
		if (Dungeon.challenges > 0) {
			addButton( curBtn = new RedButton( Messages.get(this, "challenges") ) {
				@Override
				protected void onClick() {
					hide();
					GameScene.show( new WndChallenges( Dungeon.challenges, false ) );
				}
			} );
			curBtn.icon(Icons.get(Icons.CHALLENGE_COLOR));
		}

		// Restart
		if (Dungeon.hero == null || !Dungeon.hero.isAlive()) {

			addButton( curBtn = new RedButton( Messages.get(this, "start") ) {
				@Override
				protected void onClick() {
					GamesInProgress.selectedClass = Dungeon.hero.heroClass;
					GamesInProgress.curSlot = GamesInProgress.firstEmpty();
					ShatteredPixelDungeon.switchScene(HeroSelectScene.class);
				}
			} );
			curBtn.icon(Icons.get(Icons.ENTER));
			curBtn.textColor(Window.TITLE_COLOR);
			
			addButton( curBtn = new RedButton( Messages.get(this, "rankings") ) {
				@Override
				protected void onClick() {
					InterlevelScene.mode = InterlevelScene.Mode.DESCEND;
					Game.switchScene( RankingsScene.class );
				}
			} );
			curBtn.icon(Icons.get(Icons.RANKINGS));
		}

		// Main menu
		addButton(curBtn = new RedButton(Messages.get(this, "menu")) {
			@Override
			protected void onClick() {
				try {
					Dungeon.saveAll();
				} catch (IOException e) {
					ShatteredPixelDungeon.reportException(e);
				}
				Game.switchScene(TitleScene.class);
			}
		});
		curBtn.icon(Icons.get(Icons.DISPLAY));
		if (SPDSettings.intro()) curBtn.enable(false);

		resize( WIDTH, pos );
	}
	
	@Override
	public void destroy() {
		closed = true;
		super.destroy();
	}

	private void addButton( RedButton btn ) {
		add( btn );
		btn.setRect( 0, pos > 0 ? pos += GAP : 0, WIDTH, BTN_HEIGHT );
		pos += BTN_HEIGHT;
	}

	private void addButtons( RedButton btn1, RedButton btn2 ) {
		add( btn1 );
		btn1.setRect( 0, pos > 0 ? pos += GAP : 0, (WIDTH - GAP) / 2, BTN_HEIGHT );
		add( btn2 );
		btn2.setRect( btn1.right() + GAP, btn1.top(), WIDTH - btn1.right() - GAP, BTN_HEIGHT );
		pos += BTN_HEIGHT;
	}
}
