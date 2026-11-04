// 녹픽셀 AI 감시자 - 공통 도우미

// 안전하게 요소 만들기 (텍스트는 항상 textContent로 넣는다)
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// 서버는 이 헤더가 있는 요청만 받는다 (다른 웹사이트가 몰래 보내는 요청 막기, bridge.md 3-3)
const API_HEADERS = { "Content-Type": "application/json", "X-Nokpixel-Bridge": "1" };

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: API_HEADERS,
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `요청 실패 (${response.status})`);
  return data;
}

const STATUS_TEXT = { none: "실험 없음", ready: "준비 중", running: "진행 중", finished: "완료", stopped: "중지됨", error: "오류" };

function setStatus(node, status) {
  node.className = "status " + status;
  node.textContent = STATUS_TEXT[status] || status;
}

function money(value) { return "$" + Number(value || 0).toFixed(Number(value) < 1 ? 3 : 2); }
function number(value) { return Number(value || 0).toLocaleString("ko-KR"); }

// 판단 기록 한 줄의 종류 (MVP 기준)
function entryKinds(entry) {
  const kinds = [];
  if (entry.hints && entry.hints.length) kinds.push("hint");
  if (entry.goal_changed) kinds.push("goal");
  if (entry.memo_add) kinds.push("memo");
  if (entry.memo_removed) kinds.push("memodel");
  if (entry.checkpoint) kinds.push("check");
  if (entry.basis === "추측") kinds.push("guess");
  return kinds;
}
const KIND_LABEL = { hint: "개발자 힌트", goal: "중간 목표 변경", memo: "기억 메모 추가", memodel: "🗑️ 기억 메모 지움",
  check: "큰 점검", guess: "근거: 추측", cmd: "행동" };
const BASIS_ICON = { "화면": "👀 화면에서 봄", "기록": "📒 기록·메모", "추측": "❓ 추측" };

// 생각만 하기 판의 행동 표시 (agent.py의 NOT_EXECUTED_MARK와 같은 글, AI 입력에도 붙는다)
const NOT_EXECUTED = "(실제로 실행 안 됨)";
function actionLabel(entry, config) {
  return entry.action_text + (config && config.dry_run ? " " + NOT_EXECUTED : "");
}

// 개입 횟수: 개입 규칙은 "힌트만, 조종 금지"라서 사람이 조작했을 수 있는 일시정지·F12 비상 해제도 센다.
// 기록(판단의 hints, config.json의 pauses·unlocks)에서 다시 세므로 지난 판도 같은 규칙으로 계산된다
function interventions(entries, config, pausedNow) {
  const hints = (entries || []).reduce((n, e) => n + (e.hints ? e.hints.length : 0), 0);
  const pauses = ((config && config.pauses) || []).length + ((config && config.unlocks) || []).length + (pausedNow ? 1 : 0);
  return { hints, pauses, total: hints + pauses };
}
function interventionText(n) { return `힌트 ${n.hints}회 · 일시정지 ${n.pauses}회`; }

// 생각 카드·리포트에 쓰는 되새김 한 줄
function checkLine(entry) {
  if (!entry.check_goal && !entry.basis) return null;
  return el("div", { class: "check" + (entry.basis === "추측" ? " guess" : "") },
    entry.check_goal ? el("span", {}, "🎯 ", entry.check_goal) : null,
    entry.basis ? el("span", { class: "basis", text: BASIS_ICON[entry.basis] || entry.basis }) : null);
}

// 판단 하나의 상세 (리포트 되감기, 세 창 판단 기록에서 함께 쓴다). 페이지에 d-meta … d-extra 요소가 있어야 한다.
// 기록 창·리포트·관찰 패널에서 쓰는 접힌 목표 연결 줄. open이면 펼친 채로 만든다
function checkFold(entry, open) {
  if (!entry.check_goal && !entry.basis) return null;
  const fold = el("details", { class: "checkfold" + (entry.basis === "추측" ? " guess" : "") },
    el("summary", {}, "🎯 목표 연결",
      entry.basis ? el("span", { class: "basis", text: " · 근거 " + (BASIS_ICON[entry.basis] || entry.basis) }) : null),
    entry.check_goal ? el("div", { class: "checkbody", text: entry.check_goal }) : null);
  fold.open = !!open;
  return fold;
}
function fillEntryDetail(e, config, runId) {
  const $d = (id) => document.getElementById(id);
  $d("d-meta").replaceChildren(el("div", { class: "meta" },
    el("span", { class: "tag cmd", text: `판단 ${e.step}` }),
    entryKinds(e).map((k) => el("span", { class: "tag " + k, text: KIND_LABEL[k] })),
    el("span", { text: e.time.replace("T", " ") })));
  $d("d-shot").src = `/shots/${encodeURIComponent(runId)}/${encodeURIComponent(e.image)}`;
  $d("d-thought").textContent = e.thought || "(생각 없음)";
  $d("d-checkpoint").textContent = e.checkpoint ? "🔍 큰 점검 · " + e.checkpoint : "";
  const wasOpen = !!$d("d-check").querySelector("details[open]");  // 판단을 넘겨도 펼침 상태를 유지한다
  $d("d-check").replaceChildren(...[checkFold(e, wasOpen)].filter(Boolean));
  $d("d-action").textContent = actionLabel(e, config) + (e.speech ? `  ·  💬 "${e.speech}"` : "");
  $d("d-goal").replaceChildren(e.goal ? el("span", {}, el("b", { text: "🗺️ 중간 목표 " }), e.goal + (e.goal_changed ? " (이때 바뀜)" : "")) : "");
  $d("d-extra").replaceChildren(
    e.memo_add ? el("div", { style: "color: var(--teal)" }, el("b", { text: `📝 메모 추가 ${e.memo_add_id || ""} ` }), e.memo_add) : "",
    e.memo_removed ? el("div", { style: "color: var(--teal)" }, el("b", { text: "🗑️ 메모 지움 " }), el("s", { text: e.memo_removed })) : "",
    e.hints && e.hints.length ? el("div", { style: "color: var(--purple)" }, el("b", { text: "💡 받은 힌트 " }), e.hints.join(" / ")) : "");
  fillStateDetail(e, runId);
}

// 그 판단 때의 게임 데이터 (A-6-2, docs/project/game-state.md). 게임에서 시작한 판의 state_seq가 있을 때만.
// 페이지에 d-state 요소가 있어야 한다. 이정표용 record 칸은 서버가 돌려주지 않는다
const stateCache = {};
const HUNGER_TEXT = { none: "없음", hungry: "배고픔", starving: "굶주림" };
const REASON_TEXT = { start: "판 시작", done: "행동 끝", level_changed: "층 이동", interrupted_enemy: "새 적이 보임",
  damaged: "피해", damaged_heavy: "큰 피해", interrupted: "이동이 끊김", window: "창이 뜸" };
const LOG_ICON = { good: "🟢", bad: "🔴", warning: "🟡", highlight: "🔵", normal: "·" };

async function fillStateDetail(e, runId) {
  const box = document.getElementById("d-state");
  if (!box) return;
  if (e.state_seq === undefined || e.state_seq === null) { box.replaceChildren(); box.dataset.key = ""; return; }
  const key = runId + "/" + e.state_seq;
  const wasOpen = !!box.querySelector("details[open]");
  box.dataset.key = key;
  if (!(key in stateCache)) {
    try { stateCache[key] = await api(`/api/run/${encodeURIComponent(runId)}/state/${e.state_seq}`); }
    catch (err) { return box.dataset.key === key && box.replaceChildren(el("div", { class: "muted", style: "font-size: 12.5px", text: `🗺️ 게임 데이터 #${e.state_seq}를 읽지 못했어요` })); }
  }
  if (box.dataset.key !== key) return;  // 기다리는 동안 다른 판단을 골랐다
  box.replaceChildren(stateFold(stateCache[key], wasOpen));
}

function cellText(p) { return p ? `(${p[0]},${p[1]})` : "?"; }

// 문자 지도 + 위쪽 x 눈금(5칸마다) + 왼쪽 y 숫자
function mapText(map) {
  if (!map || !map.rows || !map.rows.length) return "(본 칸 없음)";
  const [ox, oy] = map.origin, w = map.width;
  const pad = String(oy + map.rows.length - 1).length + 1;
  const ruler = Array(w).fill(" ");
  for (let i = 0; i < w; i++) {
    const x = ox + i;
    if (x % 5 === 0) String(x).split("").forEach((ch, k) => { if (i + k < w) ruler[i + k] = ch; });
  }
  return [" ".repeat(pad) + ruler.join("").trimEnd(),
    ...map.rows.map((row, j) => String(oy + j).padStart(pad - 1) + " " + row)].join("\n");
}

function stateFold(s, open) {
  const a = s.ai || {}, h = a.hero || {}, bag = a.bag || {};
  const reasons = (s.reasons || []).map((r) => REASON_TEXT[r] || r).join(", ");
  const eq = bag.equipped || {};
  const eqNames = ["weapon", "armor", "artifact", "misc", "ring"].map((k) => eq[k]).filter(Boolean)
    .map((it) => it.name + (it.cursed ? " (저주)" : ""));
  const line = (label, items) => el("div", {}, el("b", { text: label + " " }), items.length ? items.join(" · ") : "없음");
  const fold = el("details", { class: "statefold" },
    el("summary", {}, `🗺️ 그때 게임 데이터 #${s.seq}`, reasons ? el("span", { class: "muted", text: " · " + reasons }) : null),
    el("div", { class: "statebody" },
      el("div", {}, `${h.depth}층 · 체력 ${h.hp}/${h.ht} · 레벨 ${h.lvl} (경험치 ${h.exp}/${h.exp_next}) · 힘 ${h.str} · 금화 ${h.gold}`
        + ` · 배고픔 ${HUNGER_TEXT[h.hunger] || h.hunger} · 상태이상 ${(h.buffs || []).join(", ") || "없음"} · 위치 ${cellText(h.pos)} 발밑 ${h.standing_on || "?"}`),
      el("pre", { class: "statemap", text: mapText(a.map) }),
      el("div", { class: "muted", style: "font-size: 11.5px", text: "@ 나 · 1~9 적 · # 벽 · . 바닥 · + 닫힌 문 · ' 열린 문 · L 잠긴 문 · < 올라가는 계단 · > 내려가는 계단 · ~ 물 · , 풀 · \" 높은 풀 · : 낭떠러지 · ^ 함정 · T 막힌 것 · 0 우물 · * 아이템 · 빈칸 = 모름" }),
      line("보이는 적", (a.mobs || []).map((m) => `${m.mark} ${m.name} ${cellText(m.pos)}${m.side !== "enemy" ? " [" + (m.side === "ally" ? "아군" : "중립") + "]" : ""}${m.asleep ? " 잠듦" : ""} 체력 ${m.hp}`)),
      line("아이템", (a.heaps || []).map((x) => `${x.name} ${cellText(x.pos)}${x.visible_now ? "" : " (기억)"}`)),
      line("계단", (a.transitions || []).map((t) => `${t.kind === "up" ? "올라가는" : "내려가는"} ${t.name} ${cellText(t.pos)}`)),
      (a.traps || []).length ? line("함정", a.traps.map((t) => `${t.name} ${cellText(t.pos)}`)) : null,
      (a.plants || []).length ? line("식물", a.plants.map((p) => `${p.name} ${cellText(p.pos)}`)) : null,
      line("장착", eqNames),
      line("가방", (bag.items || []).map((it) => `${it.id} ${it.name}${it.cursed ? " (저주)" : ""}`)),
      (a.log || []).length ? el("div", {}, el("b", { text: "메시지" }), ...a.log.map((m) => el("div", { text: `${LOG_ICON[m.kind] || "·"} ${m.text}` }))) : null));
  fold.open = !!open;
  return fold;
}

// AI가 받은 사진 크기. config.json에 ai_image가 없으면 이전 방식(가로 720x400 창을 그대로)
function imageSizeText(config) {
  const size = config && config.ai_image;
  return size ? `${size[0]} × ${size[1]}` : "720 × 400";
}

function displayText(config) {
  if (!config.ai_image) return "720×400 (이전 방식)";
  if (!config.game_window) return config.display || "-";
  return `${config.display} · 창 ${config.game_window.join("×")} → 사진 ${config.ai_image.join("×")}`;
}

function configChips(container, config) {
  container.replaceChildren(...[
    el("span", { class: "chip" }, "플레이어 · ", el("b", { text: config.player || "-" })),
    el("span", { class: "chip" }, "모델 · ", el("b", { text: config.model_name || "-" })),
    el("span", { class: "chip" }, "공략 · ", el("b", { text: config.guide ? "제공" : "없이" })),
    config.lessons_from ? el("span", { class: "chip" }, "교훈 · ", el("b", { text: "이어받음" })) : null,
    el("span", { class: "chip mono" }, "시드 · " + (config.seed || "무작위")),
    el("span", { class: "chip mono" }, "화면 · " + displayText(config)),
    config.dry_run ? el("span", { class: "chip" }, el("b", { text: "생각만 (조작 안 함)" })) : null,
    config.demo ? el("span", { class: "chip" }, el("b", { text: "데모" })) : null,
  ].filter(Boolean));
}
