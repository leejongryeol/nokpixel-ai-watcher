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

import com.badlogic.gdx.utils.JsonValue;
import com.shatteredpixel.shatteredpixeldungeon.actors.Char;
import com.shatteredpixel.shatteredpixeldungeon.actors.buffs.Buff;
import com.shatteredpixel.shatteredpixeldungeon.actors.buffs.Hunger;
import com.shatteredpixel.shatteredpixeldungeon.actors.hero.Hero;
import com.shatteredpixel.shatteredpixeldungeon.actors.mobs.Mimic;
import com.shatteredpixel.shatteredpixeldungeon.actors.mobs.Mob;
import com.shatteredpixel.shatteredpixeldungeon.items.Heap;
import com.shatteredpixel.shatteredpixeldungeon.items.Item;
import com.shatteredpixel.shatteredpixeldungeon.levels.Level;
import com.shatteredpixel.shatteredpixeldungeon.levels.Terrain;
import com.shatteredpixel.shatteredpixeldungeon.levels.features.LevelTransition;
import com.shatteredpixel.shatteredpixeldungeon.levels.traps.Trap;
import com.shatteredpixel.shatteredpixeldungeon.plants.Plant;
import com.shatteredpixel.shatteredpixeldungeon.ui.BuffIndicator;

import java.util.ArrayList;
import java.util.List;

//[nokpixel-ai-watcher] 게임 데이터: 플레이어 화면에 보이는 것만 담는다 (docs/project/game-state.md 1·2장)
//숨기기는 모두 이 파일 안에서 한다. 숨길 값은 아예 읽지 않는다:
//  안 본 칸, 숨겨진 문·함정의 진짜 지형, 시야 밖 적, 적 수 합계, 정체 전 미믹, 아이템의 진짜 이름, 배고픔 숫자, 적 체력 숫자, 시드.
//  아이템 이름은 화면에 보이는 title()만 쓴다. 진짜 이름·클래스·감정 여부를 묻는 함수는 이 파일에서 부르지 않는다.
//주인공이 입력을 기다리는 동안(hero.ready) 렌더 스레드에서만 부른다. 그동안 액터 스레드는 멈춰 있다 (Actor.process).
public class GameState {

	public static final int VERSION = 1;
	private static final int MAX_MOB_MARKS = 9; //지도에 1~9로 적는다. 넘으면 M

	//ai 칸: AI가 볼 수 있는 데이터. 이번 단계(A-6-2)에서는 기록에만 쓰고 AI 입력에는 넣지 않는다
	public static JsonValue build( List<JsonValue> log ){
		Hero hero = Dungeon.hero;
		Level level = Dungeon.level;

		ArrayList<Mob> mobs = new ArrayList<>();
		ArrayList<Mob> chests = new ArrayList<>(); //정체 전 미믹: 화면에는 상자로 보인다
		for (Mob m : level.mobs.toArray(new Mob[0])){
			if (!seenChar(m, level)) continue;
			if (m instanceof Mimic && m.alignment == Char.Alignment.NEUTRAL) chests.add(m);
			else mobs.add(m);
		}

		JsonValue ai = object();
		ai.addChild("hero", hero(hero, level));
		ai.addChild("map", map(hero, level, mobs, chests));
		ai.addChild("mobs", mobList(mobs));
		ai.addChild("heaps", heapList(level, chests));
		ai.addChild("transitions", transitions(level));
		ai.addChild("traps", traps(level));
		ai.addChild("plants", plants(level));
		ai.addChild("bag", bag(hero));
		JsonValue logArr = array();
		for (JsonValue line : log) logArr.addChild(line);
		ai.addChild("log", logArr);
		return ai;
	}

	//사람이 칸을 살펴볼 때와 같은 조건 (GameScene.getObjectsAtCell): 지금 보이거나, 물건 같은 것(OBJECT)
	public static boolean seenChar( Char ch, Level level ){
		return ch != null && ch != Dungeon.hero && ch.pos >= 0 && ch.pos < level.length()
				&& (level.heroFOV[ch.pos] || Char.hasProp(ch, Char.Property.OBJECT));
	}

	public static boolean shown( Level level, int cell ){
		return cell >= 0 && cell < level.length() && (level.visited[cell] || level.mapped[cell]);
	}

	//겉모습 지형: 숨겨진 문은 벽, 숨겨진 함정은 바닥으로 보인다 (DungeonTileSheet, Level.tileName과 같음)
	public static int face( int terrain ){
		switch (terrain){
			case Terrain.SECRET_DOOR: return Terrain.WALL;
			case Terrain.SECRET_TRAP: return Terrain.EMPTY;
			default: return terrain;
		}
	}

	private static JsonValue hero( Hero hero, Level level ){
		JsonValue h = object();
		h.addChild("depth", new JsonValue(Dungeon.depth));
		h.addChild("hp", new JsonValue(hero.HP));
		h.addChild("ht", new JsonValue(hero.HT));
		h.addChild("lvl", new JsonValue(hero.lvl));
		h.addChild("exp", new JsonValue(hero.exp));
		h.addChild("exp_next", new JsonValue(hero.maxExp()));
		h.addChild("str", new JsonValue(hero.STR()));
		h.addChild("gold", new JsonValue(Dungeon.gold));

		//배고픔은 아이콘 단계만 화면에 보인다
		String hunger = "none";
		Hunger hg = hero.buff(Hunger.class);
		if (hg != null){
			if (hg.icon() == BuffIndicator.HUNGER) hunger = "hungry";
			else if (hg.icon() == BuffIndicator.STARVATION) hunger = "starving";
		}
		h.addChild("hunger", new JsonValue(hunger));

		//상태이상: 화면 아이콘이 있는 것만, 이름만 (남은 턴 수는 넣지 않는다)
		JsonValue buffs = array();
		for (Buff b : hero.buffs()){
			if (b instanceof Hunger || b.icon() == BuffIndicator.NONE) continue;
			buffs.addChild(new JsonValue(b.name()));
		}
		h.addChild("buffs", buffs);

		h.addChild("pos", point(level, hero.pos));
		h.addChild("standing_on", new JsonValue(level.tileName(face(level.map[hero.pos]))));
		return h;
	}

	//가 본 곳의 문자 지도: 본 칸을 모두 담는 가장 작은 네모. 안 본 칸은 공백 (game-state.md 1-4)
	private static JsonValue map( Hero hero, Level level, List<Mob> mobs, List<Mob> chests ){
		int w = level.width(), hgt = level.height();
		int left = w, top = hgt, right = -1, bottom = -1;
		for (int cell = 0; cell < level.length(); cell++){
			if (!shown(level, cell)) continue;
			int x = cell % w, y = cell / w;
			left = Math.min(left, x); right = Math.max(right, x);
			top = Math.min(top, y); bottom = Math.max(bottom, y);
		}
		JsonValue m = object();
		if (right < 0){ //본 칸이 없음 (있을 수 없지만 안전하게)
			m.addChild("origin", point(level, hero.pos));
			m.addChild("width", new JsonValue(0));
			m.addChild("height", new JsonValue(0));
			m.addChild("rows", array());
			return m;
		}

		int mw = right - left + 1, mh = bottom - top + 1;
		char[][] grid = new char[mh][mw];
		for (int y = top; y <= bottom; y++){
			for (int x = left; x <= right; x++){
				int cell = x + y * w;
				grid[y - top][x - left] = shown(level, cell) ? terrainChar(level, cell) : ' ';
			}
		}
		//겹칠 때 우선순위: @ > 적 > * > ^ > 지형 (낮은 것부터 덮어 쓴다)
		for (Trap t : level.traps.valueList()){
			if (t.visible && shown(level, t.pos)) put(grid, level, left, top, t.pos, '^');
		}
		for (Heap heap : level.heaps.valueList()){
			if (heap.seen && !heap.isEmpty()) put(grid, level, left, top, heap.pos, '*');
		}
		for (Mob c : chests) put(grid, level, left, top, c.pos, '*');
		for (int i = 0; i < mobs.size(); i++){
			put(grid, level, left, top, mobs.get(i).pos, mobMark(i));
		}
		put(grid, level, left, top, hero.pos, '@');

		JsonValue rows = array();
		for (char[] row : grid){
			//오른쪽 끝 공백은 지운다 (글자 수 줄이기)
			int end = row.length;
			while (end > 0 && row[end - 1] == ' ') end--;
			rows.addChild(new JsonValue(new String(row, 0, end)));
		}
		JsonValue origin = array();
		origin.addChild(new JsonValue(left));
		origin.addChild(new JsonValue(top));
		m.addChild("origin", origin);
		m.addChild("width", new JsonValue(mw));
		m.addChild("height", new JsonValue(mh));
		m.addChild("rows", rows);
		return m;
	}

	private static void put( char[][] grid, Level level, int left, int top, int cell, char c ){
		int x = cell % level.width() - left, y = cell / level.width() - top;
		if (y >= 0 && y < grid.length && x >= 0 && x < grid[y].length) grid[y][x] = c;
	}

	private static char mobMark( int index ){
		return index < MAX_MOB_MARKS ? (char)('1' + index) : 'M';
	}

	private static char terrainChar( Level level, int cell ){
		LevelTransition t = level.getTransition(cell);
		if (t != null) return isUp(t) ? '<' : '>';
		switch (face(level.map[cell])){
			case Terrain.WALL: case Terrain.WALL_DECO:
				return '#';
			case Terrain.DOOR:
				return '+';
			case Terrain.OPEN_DOOR:
				return '\'';
			case Terrain.LOCKED_DOOR: case Terrain.HERO_LKD_DR: case Terrain.CRYSTAL_DOOR: case Terrain.LOCKED_EXIT:
				return 'L';
			case Terrain.ENTRANCE: case Terrain.ENTRANCE_SP:
				return '<';
			case Terrain.EXIT: case Terrain.UNLOCKED_EXIT:
				return '>';
			case Terrain.WATER:
				return '~';
			case Terrain.GRASS:
				return ',';
			case Terrain.HIGH_GRASS: case Terrain.FURROWED_GRASS:
				return '"';
			case Terrain.CHASM:
				return ':';
			case Terrain.TRAP:
				return '^';
			case Terrain.WELL: case Terrain.EMPTY_WELL: case Terrain.ALCHEMY:
				return '0';
			case Terrain.STATUE: case Terrain.STATUE_SP: case Terrain.BOOKSHELF: case Terrain.BARRICADE:
			case Terrain.REGION_DECO: case Terrain.REGION_DECO_ALT: case Terrain.CUSTOM_DECO: case Terrain.CUSTOM_DECO_WTR:
			case Terrain.MINE_CRYSTAL: case Terrain.MINE_BOULDER:
				return 'T';
			case Terrain.EMPTY: case Terrain.EMPTY_SP: case Terrain.EMPTY_DECO: case Terrain.CUSTOM_DECO_EMPTY:
			case Terrain.INACTIVE_TRAP: case Terrain.EMBERS: case Terrain.PEDESTAL:
				return '.';
			default:
				return '?';
		}
	}

	private static boolean isUp( LevelTransition t ){
		return t.type == LevelTransition.Type.REGULAR_ENTRANCE || t.type == LevelTransition.Type.SURFACE
				|| t.type == LevelTransition.Type.BRANCH_ENTRANCE;
	}

	private static JsonValue mobList( List<Mob> mobs ){
		JsonValue arr = array();
		Level level = Dungeon.level;
		for (int i = 0; i < mobs.size(); i++){
			Mob m = mobs.get(i);
			JsonValue o = object();
			o.addChild("mark", new JsonValue(String.valueOf(mobMark(i))));
			o.addChild("name", new JsonValue(m.name()));
			o.addChild("pos", point(level, m.pos));
			o.addChild("side", new JsonValue(m.alignment == Char.Alignment.ENEMY ? "enemy"
					: m.alignment == Char.Alignment.ALLY ? "ally" : "neutral"));
			o.addChild("asleep", new JsonValue(m.state == m.SLEEPING)); //머리 위 Zz로 보인다
			o.addChild("hp", new JsonValue(quarters(m.HP, m.HT))); //체력 막대처럼 4단계만
			arr.addChild(o);
		}
		return arr;
	}

	//체력 4단계: "4/4" ~ "1/4" (살아 있으면 1 이상)
	private static String quarters( int hp, int ht ){
		if (ht <= 0) return "?";
		int q = (int)Math.ceil(4f * Math.max(0, hp) / ht);
		q = Math.max(hp > 0 ? 1 : 0, Math.min(4, q));
		return q + "/4";
	}

	private static JsonValue heapList( Level level, List<Mob> chests ){
		JsonValue arr = array();
		for (Heap heap : level.heaps.valueList()){
			if (!heap.seen || heap.isEmpty()) continue;
			JsonValue o = object();
			o.addChild("name", new JsonValue(heap.title()));
			o.addChild("pos", point(level, heap.pos));
			o.addChild("visible_now", new JsonValue(level.heroFOV[heap.pos]));
			arr.addChild(o);
		}
		for (Mob c : chests){
			JsonValue o = object();
			o.addChild("name", new JsonValue(c.name())); //정체 전 미믹의 name()은 "상자"
			o.addChild("pos", point(level, c.pos));
			o.addChild("visible_now", new JsonValue(level.heroFOV[c.pos]));
			arr.addChild(o);
		}
		return arr;
	}

	//본 칸에 있는 계단만. 게임의 이름 그대로와 올라감/내려감만 준다 (우리 설명은 붙이지 않는다)
	private static JsonValue transitions( Level level ){
		JsonValue arr = array();
		for (LevelTransition t : level.transitions){
			int seen = -1;
			if (shown(level, t.cell())) seen = t.cell();
			else {
				for (int cell = 0; cell < level.length() && seen < 0; cell++){
					if (t.inside(cell) && shown(level, cell)) seen = cell;
				}
			}
			if (seen < 0) continue;
			JsonValue o = object();
			o.addChild("kind", new JsonValue(isUp(t) ? "up" : "down"));
			o.addChild("name", new JsonValue(level.tileName(face(level.map[seen]))));
			o.addChild("pos", point(level, seen));
			arr.addChild(o);
		}
		return arr;
	}

	private static JsonValue traps( Level level ){
		JsonValue arr = array();
		for (Trap t : level.traps.valueList()){
			if (!t.visible || !shown(level, t.pos)) continue;
			JsonValue o = object();
			o.addChild("name", new JsonValue(t.name()));
			o.addChild("pos", point(level, t.pos));
			arr.addChild(o);
		}
		return arr;
	}

	private static JsonValue plants( Level level ){
		JsonValue arr = array();
		for (Plant p : level.plants.valueList()){
			if (!shown(level, p.pos)) continue;
			JsonValue o = object();
			o.addChild("name", new JsonValue(p.name()));
			o.addChild("pos", point(level, p.pos));
			arr.addChild(o);
		}
		return arr;
	}

	//가방: 화면 이름(title())과 아이템 창 버튼 이름만. 번호는 이 상태 안에서만 쓰는 번호
	private static JsonValue bag( Hero hero ){
		JsonValue b = object();
		JsonValue eq = object();
		eq.addChild("weapon", itemName(hero.belongings.weapon()));
		eq.addChild("armor", itemName(hero.belongings.armor()));
		eq.addChild("artifact", itemName(hero.belongings.artifact()));
		eq.addChild("misc", itemName(hero.belongings.misc()));
		eq.addChild("ring", itemName(hero.belongings.ring()));
		b.addChild("equipped", eq);

		JsonValue items = array();
		int id = 1;
		for (Item item : hero.belongings.backpack){
			JsonValue o = object();
			o.addChild("id", new JsonValue(id++));
			o.addChild("name", new JsonValue(item.title()));
			if (item.visiblyCursed()) o.addChild("cursed", new JsonValue(true));
			JsonValue actions = array();
			for (String action : item.actions(hero)){
				actions.addChild(new JsonValue(item.actionName(action, hero)));
			}
			o.addChild("actions", actions);
			items.addChild(o);
		}
		b.addChild("items", items);
		return b;
	}

	private static JsonValue itemName( Item item ){
		if (item == null) return new JsonValue(JsonValue.ValueType.nullValue);
		JsonValue o = object();
		o.addChild("name", new JsonValue(item.title()));
		if (item.visiblyCursed()) o.addChild("cursed", new JsonValue(true)); //저주가 화면에 드러났을 때만
		return o;
	}

	public static JsonValue point( Level level, int cell ){
		JsonValue p = array();
		p.addChild(new JsonValue(cell % level.width()));
		p.addChild(new JsonValue(cell / level.width()));
		return p;
	}

	public static JsonValue object(){
		return new JsonValue(JsonValue.ValueType.object);
	}

	public static JsonValue array(){
		return new JsonValue(JsonValue.ValueType.array);
	}
}
