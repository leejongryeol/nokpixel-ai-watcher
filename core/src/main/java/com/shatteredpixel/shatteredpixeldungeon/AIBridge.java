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
import com.watabou.noosa.Game;
import com.watabou.utils.Callback;

import java.io.File;

//[nokpixel-ai-watcher] 게임 → AI 관찰기(ai-bridge/web.py) 통로 (docs/project/bridge.md 3장)
//게임이 묻고 Python이 답한다. 응답은 다른 스레드에서 오므로 렌더 스레드로 넘겨서 돌려준다.
//실패, 시간 초과, 이상한 응답은 모두 null로 돌려준다. 어떤 경우에도 게임을 멈추거나 끄지 않는다.
public class AIBridge {

	public static final String HOST = "http://127.0.0.1:8765";
	public static final int SHORT_TIMEOUT = 3000; //상태 조회·키 보내기·판 준비 (ms)
	public static final int TEST_TIMEOUT = 35000; //연결 시험: Python이 최대 30초 + 여유

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
