// 중계 서버 테스트 (진짜 Claude API 대신 가짜로 응답)  실행: node server/test.mjs
import worker from "./worker.js";
import assert from "node:assert/strict";

const calls = [];
globalThis.fetch = async (url, init) => {
  const body = JSON.parse(init.body);
  calls.push({ url, headers: init.headers, body });
  if (init.headers["x-api-key"] === "bad") {
    return new Response(JSON.stringify({ error: { message: "invalid x-api-key" } }), { status: 401 });
  }
  const isOcr = Array.isArray(body.messages[0].content);
  const text = isOcr ? "# 영수증\n- 커피 4,500원" : 'OK {"action":"bundle","files":["*.jpg"],"out":"묶음.pptx"}';
  return new Response(JSON.stringify({ content: [{ type: "text", text }] }), { status: 200 });
};

const env = { ANTHROPIC_API_KEY: "test-key", PLAN_MODEL: "m-plan", OCR_MODEL: "m-ocr" };
const call = (path, body, e = env, method = "POST", headers = {}) =>
  worker.fetch(new Request("https://relay.example" + path, {
    method, headers: { "Content-Type": "application/json", Origin: "https://site.example", ...headers },
    body: method === "POST" ? JSON.stringify(body) : undefined,
  }), e);

let r = await call("/health", null, env, "GET");
assert.equal(r.status, 200); assert.deepEqual(await r.json(), { ok: true, ai: true });
assert.equal(r.headers.get("Access-Control-Allow-Origin"), "https://site.example");

r = await call("/plan", { text: "사진 ppt로", files: ["a.jpg", "b.jpg"] });
assert.equal(r.status, 200);
assert.deepEqual((await r.json()).plan, { action: "bundle", files: ["*.jpg"], out: "묶음.pptx" });
const last = calls.at(-1);
assert.equal(last.url, "https://api.anthropic.com/v1/messages");
assert.equal(last.headers["x-api-key"], "test-key");
assert.equal(last.headers["anthropic-version"], "2023-06-01");
assert.equal(last.body.model, "m-plan");
assert.match(last.body.messages[0].content, /a\.jpg\nb\.jpg/);

r = await call("/plan", { text: "x".repeat(5000), files: [] });
assert.equal(calls.at(-1).body.messages[0].content.endsWith("x".repeat(500)), true, "긴 문장 잘림");

r = await call("/ocr", { image: "aGVsbG8=", media_type: "image/png" });
assert.equal(r.status, 200); assert.equal((await r.json()).text, "# 영수증\n- 커피 4,500원");
assert.equal(calls.at(-1).body.model, "m-ocr");
assert.equal(calls.at(-1).body.messages[0].content[0].source.media_type, "image/png");

r = await call("/ocr", { image: "x".repeat(7_000_001) });           assert.equal(r.status, 413);
r = await call("/ocr", { image: "aa", media_type: "text/html" });   assert.equal(r.status, 400);
r = await call("/plan", { text: "  " });                            assert.equal(r.status, 400);
r = await call("/chat", { text: "hi" });                            assert.equal(r.status, 404);
r = await call("/plan", { text: "hi" }, { ANTHROPIC_API_KEY: "" }); assert.equal(r.status, 500);
r = await call("/plan", { text: "hi" }, { ANTHROPIC_API_KEY: "bad" });
assert.equal(r.status, 502); assert.match((await r.json()).error, /invalid x-api-key/);

let n = 0;
const limited = { ...env, LIMITER: { limit: async () => ({ success: ++n <= 2 }) } };
assert.equal((await call("/plan", { text: "a" }, limited)).status, 200);
assert.equal((await call("/plan", { text: "a" }, limited)).status, 200);
assert.equal((await call("/plan", { text: "a" }, limited)).status, 429);

r = await call("/plan", { text: "a" }, { ...env, ALLOWED_ORIGINS: "https://mine.example" });
assert.equal(r.headers.get("Access-Control-Allow-Origin"), "null");
r = await call("/plan", { text: "a" }, { ...env, ALLOWED_ORIGINS: "https://site.example" });
assert.equal(r.headers.get("Access-Control-Allow-Origin"), "https://site.example");
r = await call("/plan", null, env, "OPTIONS");                       assert.equal(r.status, 204);

console.log("중계 서버 테스트 전부 통과");
