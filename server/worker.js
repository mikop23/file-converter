/**
 * 파일 변환기 중계 서버 (Cloudflare Worker)
 *
 * 하는 일: 앱/사이트가 보낸 요청을 Claude API로 전달. API 키는 여기에만 있음.
 * 허용하는 일은 두 가지뿐 (아무 대화나 시키는 용도로 못 씀):
 *   POST /plan  {text, files}          → 파일 변환 계획(JSON)
 *   POST /ocr   {image, media_type}    → 이미지 속 글자(마크다운)
 *   GET  /health                       → 상태 확인
 *
 * 비밀값: ANTHROPIC_API_KEY  (wrangler secret put ANTHROPIC_API_KEY)
 * 설정값: PLAN_MODEL, OCR_MODEL, ALLOWED_ORIGINS (wrangler.toml)
 */

const PLAN_SYSTEM = `너는 파일 변환 도우미다. 사용자 요청을 아래 JSON 하나로만 답한다. 설명 금지.

가능한 action:
1) "bundle": 이미지 여러 장을 하나로 묶기. out 확장자는 pdf/docx/pptx/zip 중 하나.
   {"action":"bundle","files":["*.jpg"],"out":"묶음.pdf","sort":"name"|"time","quality":80,"max_size":2000,"per_page":1}
2) "convert": 문서를 다른 형식으로. target은 docx/pdf/md/html/txt/odt/epub 중 하나.
   {"action":"convert","files":["보고서.md"],"target":"docx"}
3) "split": PDF를 페이지별 이미지로.
   {"action":"split","files":["스캔.pdf"],"format":"jpg"|"png"}
4) "ocr": 사진/스캔 PDF 속 글자를 뽑아 문서로. target은 docx/txt/md 중 하나.
   {"action":"ocr","files":["영수증.jpg"],"target":"docx"}
5) "imgconv": 사진을 다른 사진 형식으로 (한 장씩). target은 jpg/png/webp 중 하나.
   {"action":"imgconv","files":["*.png"],"target":"jpg"}
6) "unknown": 위로 처리 못하는 요청. {"action":"unknown","reason":"..."}

규칙:
- files에는 '폴더 파일 목록'에 있는 이름이나 와일드카드(*.jpg)만 쓴다.
- "사진/이미지 전부" → 이미지 와일드카드. "찍은 순/시간순" → sort "time".
- "용량 줄여/작게" → quality 60, max_size 1500. "고화질/원본" → quality 95, max_size 0.
- "한 페이지에 N장" → per_page N.
- "글자 뽑아/텍스트로/타이핑해/OCR/받아적어" → ocr.
- 출력 파일명을 말 안 하면 적당한 한국어 이름을 짓는다.`;

const OCR_PROMPT = `이 이미지에 있는 글자를 전부 그대로 옮겨 적어라.
- 원래 순서와 줄바꿈, 문단을 유지한다.
- 제목은 #, 목록은 -, 표는 마크다운 표로 쓴다.
- 손글씨도 최대한 읽는다. 못 읽는 글자는 [?]로 쓴다.
- 글자를 옮긴 것 외에 설명, 인사, 요약은 절대 쓰지 않는다.
- 글자가 하나도 없으면 빈 문자열만 답한다.`;

const LIMITS = { text: 500, files: 300, fileName: 200, imageBase64: 7_000_000 };
const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);

function cors(req, env) {
  const origin = req.headers.get("Origin") || "";
  const allowed = (env.ALLOWED_ORIGINS || "*").split(",").map((s) => s.trim());
  const ok = allowed.includes("*") || allowed.includes(origin);
  return {
    "Access-Control-Allow-Origin": ok ? origin || "*" : "null",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function json(data, status, headers) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...headers },
  });
}

async function claude(env, model, system, content, maxTokens) {
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model,
      max_tokens: maxTokens,
      ...(system ? { system } : {}),
      messages: [{ role: "user", content }],
    }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = data?.error?.message || `HTTP ${r.status}`;
    throw Object.assign(new Error("AI 서버 오류: " + msg), { status: r.status === 429 ? 429 : 502 });
  }
  return (data.content || []).filter((b) => b.type === "text").map((b) => b.text).join("");
}

async function handlePlan(body, env) {
  const text = String(body.text || "").slice(0, LIMITS.text);
  const files = Array.isArray(body.files) ? body.files.slice(0, LIMITS.files) : [];
  if (!text.trim()) throw Object.assign(new Error("요청 문장이 비어 있어요"), { status: 400 });
  const listing = files.map((f) => String(f).slice(0, LIMITS.fileName)).join("\n") || "(비어 있음)";
  const out = await claude(
    env, env.PLAN_MODEL || "claude-haiku-5-5", PLAN_SYSTEM,
    `폴더 파일 목록:\n${listing}\n\n요청: ${text}`, 400,
  );
  const m = out.match(/\{[\s\S]*\}/);
  if (!m) throw Object.assign(new Error("AI 답을 해석하지 못했어요"), { status: 502 });
  return { plan: JSON.parse(m[0]) };
}

async function handleOcr(body, env) {
  const image = String(body.image || "");
  const mediaType = String(body.media_type || "image/jpeg");
  if (!image) throw Object.assign(new Error("이미지가 없어요"), { status: 400 });
  if (image.length > LIMITS.imageBase64) throw Object.assign(new Error("이미지가 너무 커요 (5MB 이하)"), { status: 413 });
  if (!IMAGE_TYPES.has(mediaType)) throw Object.assign(new Error("지원하지 않는 이미지 형식"), { status: 400 });
  const text = await claude(
    env, env.OCR_MODEL || "claude-sonnet-5-5", null,
    [
      { type: "image", source: { type: "base64", media_type: mediaType, data: image } },
      { type: "text", text: OCR_PROMPT },
    ],
    4096,
  );
  return { text: text.trim() };
}

export default {
  async fetch(req, env) {
    const h = cors(req, env);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: h });
    const path = new URL(req.url).pathname.replace(/\/+$/, "");

    if (req.method === "GET" && (path === "" || path === "/health")) {
      return json({ ok: true, ai: Boolean(env.ANTHROPIC_API_KEY) }, 200, h);
    }
    if (req.method !== "POST" || !["/plan", "/ocr"].includes(path)) {
      return json({ error: "없는 주소예요" }, 404, h);
    }
    if (!env.ANTHROPIC_API_KEY) return json({ error: "서버에 API 키가 설정되지 않았어요" }, 500, h);

    // 사용량 제한: 같은 IP에서 1분에 N번까지 (wrangler.toml의 LIMITER)
    if (env.LIMITER) {
      const ip = req.headers.get("CF-Connecting-IP") || "unknown";
      const { success } = await env.LIMITER.limit({ key: `${path}:${ip}` });
      if (!success) return json({ error: "요청이 너무 많아요. 잠시 후 다시 해주세요" }, 429, h);
    }

    try {
      const body = await req.json();
      const result = path === "/plan" ? await handlePlan(body, env) : await handleOcr(body, env);
      return json(result, 200, h);
    } catch (e) {
      return json({ error: e.message || "오류" }, e.status || 500, h);
    }
  },
};
