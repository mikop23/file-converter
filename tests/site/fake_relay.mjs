import http from "node:http";
import worker from "../../server/worker.js";
globalThis.fetch = async (url, init) => {
  const b = JSON.parse(init.body);
  if (Array.isArray(b.messages[0].content)) return new Response(JSON.stringify({ content: [{ type: "text", text: "# 스캔 문서\n\n| 품목 | 가격 |\n|---|---|\n| 커피 | 4,500원 |\n\n- 메모" }] }));
  const t = b.messages[0].content;
  const plan = t.includes("글자") ? { action: "ocr", files: ["스캔.pdf"], target: "docx" } : { action: "split", files: ["사진1.jpg"], format: "jpg" }; // 일부러 틀린 답 → 보정 확인
  return new Response(JSON.stringify({ content: [{ type: "text", text: JSON.stringify(plan) }] }));
};
http.createServer(async (req, res) => {
  const chunks = []; for await (const c of req) chunks.push(c);
  const r = await worker.fetch(new Request("http://x" + req.url, { method: req.method, headers: req.headers, body: ["POST"].includes(req.method) ? Buffer.concat(chunks) : undefined }), { ANTHROPIC_API_KEY: "k" });
  res.writeHead(r.status, Object.fromEntries(r.headers)); res.end(Buffer.from(await r.arrayBuffer()));
}).listen(18788);
