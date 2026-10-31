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

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
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

// 생각 카드·리포트에 쓰는 되새김 한 줄
function checkLine(entry) {
  if (!entry.check_goal && !entry.basis) return null;
  return el("div", { class: "check" + (entry.basis === "추측" ? " guess" : "") },
    entry.check_goal ? el("span", {}, "🎯 ", entry.check_goal) : null,
    entry.basis ? el("span", { class: "basis", text: BASIS_ICON[entry.basis] || entry.basis }) : null);
}

// 판단 하나의 상세 (리포트 되감기, 세 창 판단 기록에서 함께 쓴다). 페이지에 d-meta … d-extra 요소가 있어야 한다.
function fillEntryDetail(e, config, runId) {
  const $d = (id) => document.getElementById(id);
  $d("d-meta").replaceChildren(el("div", { class: "meta" },
    el("span", { class: "tag cmd", text: `판단 ${e.step}` }),
    entryKinds(e).map((k) => el("span", { class: "tag " + k, text: KIND_LABEL[k] })),
    el("span", { text: e.time.replace("T", " ") })));
  $d("d-shot").src = `/shots/${encodeURIComponent(runId)}/${encodeURIComponent(e.image)}`;
  $d("d-thought").textContent = e.thought || "(생각 없음)";
  $d("d-checkpoint").textContent = e.checkpoint ? "🔍 큰 점검 · " + e.checkpoint : "";
  $d("d-check").replaceChildren(...[checkLine(e)].filter(Boolean));
  $d("d-action").textContent = actionLabel(e, config) + (e.speech ? `  ·  💬 "${e.speech}"` : "");
  $d("d-goal").replaceChildren(e.goal ? el("span", {}, el("b", { text: "🗺️ 중간 목표 " }), e.goal + (e.goal_changed ? " (이때 바뀜)" : "")) : "");
  $d("d-extra").replaceChildren(
    e.memo_add ? el("div", { style: "color: var(--teal)" }, el("b", { text: `📝 메모 추가 ${e.memo_add_id || ""} ` }), e.memo_add) : "",
    e.memo_removed ? el("div", { style: "color: var(--teal)" }, el("b", { text: "🗑️ 메모 지움 " }), el("s", { text: e.memo_removed })) : "",
    e.hints && e.hints.length ? el("div", { style: "color: var(--purple)" }, el("b", { text: "💡 받은 힌트 " }), e.hints.join(" / ")) : "");
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
