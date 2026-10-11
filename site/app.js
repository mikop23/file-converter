// 파일 변환기 - 사이트 버전. 모든 변환은 이 브라우저 안에서 처리 (글자 추출·온라인 AI만 서버 사용)
import { IMG_EXT, DOC_EXT, ext, rulesPlan, fixPlan, check, describe } from "./planner.js";
import * as pdfjs from "./vendor/pdf.min.mjs";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("./vendor/pdf.worker.min.mjs", import.meta.url).href;

const $ = (s) => document.querySelector(s);
const QUALITY = { normal: [0.8, 2000], small: [0.6, 1500], hq: [0.95, 0] };
const state = { files: [], busy: false, aiOnline: false, nextId: 1 };
const TOUCH = matchMedia("(pointer: coarse)").matches;                // 폰·태블릿 (끌어서 순서 바꾸기 안 됨)

// ───────── 저장소 (실패해도 동작) ─────────
const store = {
  get(k) { try { return localStorage.getItem("fconv." + k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem("fconv." + k, v); } catch { /* 무시 */ } },
};
const relayUrl = () => (store.get("relay") ?? window.FCONV_CONFIG?.relayUrl ?? "").replace(/\/+$/, "");

// ───────── 상태 표시 ─────────
function msg(text, kind = "") { const m = $("#msg"); m.textContent = text; m.className = kind; }
function busy(on, text) {
  state.busy = on;
  $("#bar").hidden = !on;
  $("#bar").classList.remove("det");
  $("#bar i").style.width = "";
  if (on) msg(text);
  refresh();
}
function progress(done, total, label) {
  const b = $("#bar"); b.classList.add("det");
  $("#bar i").style.width = `${Math.round((done / total) * 100)}%`;
  msg(`${label} ${done}/${total}`);
}
const fmtSize = (n) => (n > 1048576 ? (n / 1048576).toFixed(1) + "MB" : Math.max(1, Math.round(n / 1024)) + "KB");

function deliver(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name;
  a.innerHTML = `<span></span><small>${fmtSize(blob.size)}</small>`;
  a.querySelector("span").textContent = "↓ " + name;
  $("#results").prepend(a);
  a.click();                                  // 바로 다운로드 + 목록에도 남김
  return a;
}

// ───────── 파일 목록 ─────────
const kindOf = (name) => (IMG_EXT.includes(ext(name)) ? "image" : ext(name) === "pdf" ? "pdf" : DOC_EXT.includes(ext(name)) ? "doc" : null);

function addFiles(list) {
  let skipped = 0;
  for (const file of list) {
    const kind = kindOf(file.name);
    if (!kind) { skipped++; continue; }
    if (state.files.some((f) => f.file.name === file.name && f.file.size === file.size)) continue;
    state.files.push({ id: state.nextId++, file, name: file.name, kind, thumb: kind === "image" ? URL.createObjectURL(file) : null });
  }
  render();
  if (skipped) msg(`지원하지 않는 파일 ${skipped}개는 뺐어요 (HEIC는 사진 앱에서 JPG로 바꿔 넣어주세요).`, "err");
}

function render() {
  const ol = $("#list");
  ol.replaceChildren(...state.files.map((f, i) => {
    const li = document.createElement("li");
    li.draggable = true; li.dataset.id = f.id;
    const thumb = f.thumb ? Object.assign(document.createElement("img"), { src: f.thumb, alt: "", className: "thumb", loading: "lazy" })
                          : Object.assign(document.createElement("span"), { className: "thumb", textContent: ext(f.name) });
    if (f.kind === "image") thumb.style.transform = `rotate(${f.rot || 0}deg)`;
    const name = Object.assign(document.createElement("span"), { className: "fname", textContent: f.name, title: f.name });
    const rot = Object.assign(document.createElement("button"), { className: "rot", type: "button", textContent: "⟳", title: "오른쪽으로 90° 돌리기" });
    rot.setAttribute("aria-label", f.name + " 돌리기");
    if (f.kind !== "image") { rot.style.visibility = "hidden"; rot.tabIndex = -1; }   // 자리는 남겨서 × 줄 맞춤
    rot.onclick = () => { f.rot = ((f.rot || 0) + 90) % 360; thumb.style.transform = `rotate(${f.rot}deg)`; refresh(); };
    const rm = Object.assign(document.createElement("button"), { className: "rm", type: "button", textContent: "×", title: "빼기" });
    rm.setAttribute("aria-label", f.name + " 빼기");
    rm.onclick = () => { state.files = state.files.filter((x) => x !== f); render(); };
    li.append(Object.assign(document.createElement("span"), { className: "idx", textContent: i + 1 }), thumb, name,
              Object.assign(document.createElement("span"), { className: "fsize", textContent: fmtSize(f.file.size) }), rot, rm);
    return li;
  }));
  $("#drop").classList.toggle("has", state.files.length > 0);
  $("#empty").hidden = state.files.length > 0;
  const n = (k) => state.files.filter((f) => f.kind === k).length;
  $("#count").textContent = state.files.length ? `이미지 ${n("image")} · PDF ${n("pdf")} · 문서 ${n("doc")}` : "";
  refresh();
}

function refresh() {
  const n = (k) => state.files.filter((f) => f.kind === k).length;
  const has = { image: n("image") > 0, pdf: n("pdf") > 0, doc: n("doc") > 0 };
  const dis = (el, off) => { el.disabled = state.busy || off; };
  document.querySelectorAll("[data-bundle], [data-imgconv]").forEach((b) => dis(b, !has.image));
  dis($("#convBtn"), !has.doc);
  dis($("#splitBtn"), !has.pdf);
  dis($("#askBtn"), !state.files.length);
  const ocrReady = (has.image || has.pdf) && state.aiOnline;
  dis($("#ocrBtn"), !ocrReady);
  // 지금 못 쓰는 카드는 흐리게 + 이유 보여주기
  document.querySelectorAll("[data-why]").forEach((w) => { w.hidden = has[w.dataset.why]; w.closest(".card").classList.toggle("off", !has[w.dataset.why]); });
  $("#imgConvTip").hidden = n("image") < 4;
  $("#trayTip").hidden = state.files.length < 2 && !has.image;
  $("#trayTip").textContent = (TOUCH ? "순서는 '사진 한 파일로 합치기'의 순서 옵션(파일 이름순·찍은 시간순)으로 정할 수 있어요."
                                     : "줄을 끌어서 순서를 바꿀 수 있어요.") + " 누운 사진은 ⟳를 눌러 돌리세요. 만드는 파일에 그대로 들어가요.";
  $("#ocrSec").classList.toggle("off", !ocrReady);
  $("#ocrNote").textContent = !relayUrl() ? "⚙ 설정에서 AI를 연결하면 쓸 수 있어요."
    : !state.aiOnline ? "AI에 연결이 안 돼요. 인터넷을 확인해주세요."
    : !(has.image || has.pdf) ? "사진이나 PDF를 넣으면 쓸 수 있어요."
    : "사진 내용이 AI로 전송돼서 읽혀요.";
  $("#askWhy").textContent = state.aiOnline ? "AI가 켜져 있어서 자유롭게 써도 알아들어요."
    : "지금은 간단한 문장만 알아들어요. (형식 이름과 '합쳐줘·바꿔줘·쪼개줘' 같은 말)";
}

// 끌어서 순서 바꾸기
let dragId = null;
$("#list").addEventListener("dragstart", (e) => { const li = e.target.closest("li"); if (!li) return; dragId = +li.dataset.id; li.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", ""); });
$("#list").addEventListener("dragend", () => { dragId = null; document.querySelectorAll("#list li").forEach((l) => l.classList.remove("dragging", "drop-before")); });
$("#list").addEventListener("dragover", (e) => {
  if (dragId == null) return;
  e.preventDefault();
  document.querySelectorAll("#list li").forEach((l) => l.classList.remove("drop-before"));
  e.target.closest("li")?.classList.add("drop-before");
});
$("#list").addEventListener("drop", (e) => {
  if (dragId == null) return;
  e.preventDefault(); e.stopPropagation();
  const target = e.target.closest("li");
  const from = state.files.findIndex((f) => f.id === dragId);
  const [moved] = state.files.splice(from, 1);
  const to = target ? state.files.findIndex((f) => f.id === +target.dataset.id) : state.files.length;
  state.files.splice(to < 0 ? state.files.length : to, 0, moved);
  render();
});
// 바깥에서 파일 끌어오기
const drop = $("#drop");
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { if (dragId != null || !e.dataTransfer.types.includes("Files")) return; e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("over")));
drop.addEventListener("drop", (e) => { if (dragId != null || !e.dataTransfer.files.length) return; e.preventDefault(); addFiles(e.dataTransfer.files); });
$("#pick").addEventListener("change", (e) => { addFiles(e.target.files); e.target.value = ""; });
$("#clear").onclick = () => { state.files = []; render(); };

// ───────── 사진 그리기: EXIF 회전 보정 + 손으로 돌린 각도 + 크기 줄이기 ─────────
async function drawImage(f, { maxSide = 0, fill = null } = {}) {
  const bmp = await createImageBitmap(f.file, { imageOrientation: "from-image" });   // 폰 사진 눕는 문제 해결
  const rot = f.rot || 0, turn = rot % 180 !== 0;
  let w = bmp.width, h = bmp.height;
  if (maxSide && Math.max(w, h) > maxSide) { const k = maxSide / Math.max(w, h); w = Math.round(w * k); h = Math.round(h * k); }
  const c = new OffscreenCanvas(turn ? h : w, turn ? w : h);
  const g = c.getContext("2d");
  if (fill) { g.fillStyle = fill; g.fillRect(0, 0, c.width, c.height); }
  g.translate(c.width / 2, c.height / 2);
  g.rotate((rot * Math.PI) / 180);
  g.drawImage(bmp, -w / 2, -h / 2, w, h);
  bmp.close();
  return c;
}

async function prepareImage(f, quality = "normal") {
  const [q, maxSide] = QUALITY[quality] || QUALITY.normal;
  const c = await drawImage(f, { maxSide, fill: "#fff" });                          // 투명 PNG는 흰 배경
  const blob = await c.convertToBlob({ type: "image/jpeg", quality: q });
  return { w: c.width, h: c.height, blob, bytes: new Uint8Array(await blob.arrayBuffer()) };
}

async function takenTime(f) {
  try { const t = await exifr.parse(f.file, ["DateTimeOriginal", "CreateDate"]); const d = t?.DateTimeOriginal || t?.CreateDate; if (d) return +new Date(d); } catch { /* EXIF 없음 */ }
  return f.file.lastModified;
}
const naturalKey = (a, b) => a.name.localeCompare(b.name, "ko", { numeric: true, sensitivity: "base" });

async function ordered(items, sort) {
  if (sort === "name") return [...items].sort(naturalKey);
  if (sort === "time") {
    const t = new Map(await Promise.all(items.map(async (f) => [f, await takenTime(f)])));
    return [...items].sort((a, b) => t.get(a) - t.get(b));
  }
  return items;                                            // 목록 순서 그대로
}
const toB64 = (bytes) => { let s = ""; for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000)); return btoa(s); };

// ───────── ① 이미지 묶기 ─────────
async function bundle(items, out, { sort = "none", quality = "normal", perPage = 1 } = {}) {
  items = await ordered(items, sort);
  const kind = ext(out);
  const imgs = [];
  for (const [i, f] of items.entries()) { progress(i, items.length, "사진 준비 중…"); imgs.push({ ...(await prepareImage(f, quality)), name: f.name }); }
  progress(items.length, items.length, "파일 만드는 중…");
  let blob;
  if (kind === "pdf") {
    const pt = (px) => (px * 72) / 150;                    // 150dpi 기준 페이지 크기
    const { jsPDF } = window.jspdf;
    let doc;
    for (const im of imgs) {
      const size = [pt(im.w), pt(im.h)], o = im.w > im.h ? "l" : "p";
      if (!doc) doc = new jsPDF({ unit: "pt", format: size, orientation: o, compress: true });
      else doc.addPage(size, o);
      doc.addImage(im.bytes, "JPEG", 0, 0, size[0], size[1], undefined, "FAST");
    }
    blob = doc.output("blob");
  } else if (kind === "pptx") {
    const pptx = new PptxGenJS();
    pptx.layout = "LAYOUT_WIDE";                            // 16:9 (13.33 × 7.5 in)
    const W = 13.333, H = 7.5;
    for (const im of imgs) {
      const s = Math.min(W / im.w, H / im.h), w = im.w * s, h = im.h * s;
      pptx.addSlide().addImage({ data: "data:image/jpeg;base64," + toB64(im.bytes), x: (W - w) / 2, y: (H - h) / 2, w, h });
    }
    blob = await pptx.write({ outputType: "blob" });
  } else if (kind === "docx") {
    const { Document, Packer, Paragraph, ImageRun, PageBreak, AlignmentType } = docx;
    const usableW = 680, usableH = 980 / perPage;           // A4, 여백 1.5cm (96dpi 기준 픽셀)
    const children = [];
    imgs.forEach((im, i) => {
      const s = Math.min(usableW / im.w, (usableH * 0.95) / im.h);
      children.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new ImageRun({ data: im.bytes, transformation: { width: Math.round(im.w * s), height: Math.round(im.h * s) } })] }));
      if ((i + 1) % perPage === 0 && i + 1 < imgs.length) children.push(new Paragraph({ children: [new PageBreak()] }));
    });
    const cm = 567;                                         // 1cm = 567 twip
    blob = await Packer.toBlob(new Document({ sections: [{ properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1.5 * cm, bottom: 1.5 * cm, left: 1.5 * cm, right: 1.5 * cm } } }, children }] }));
  } else if (kind === "zip") {
    const z = new JSZip();
    imgs.forEach((im, i) => z.file(`${String(i + 1).padStart(3, "0")}_${im.name.replace(/\.[^.]+$/, "")}.jpg`, im.bytes));
    blob = await z.generateAsync({ type: "blob" });
  } else throw new Error(kind + " 로 묶기는 지원하지 않아요");
  return deliver(blob, out);
}

// ───────── ①-2 사진 형식 바꾸기 ─────────
const IMG_MIME = { jpg: "image/jpeg", png: "image/png", webp: "image/webp" };
async function convertImages(items, fmt) {
  const outs = [];
  for (const [i, f] of items.entries()) {
    progress(i, items.length, "사진 바꾸는 중…");
    const c = await drawImage(f, { fill: fmt === "jpg" ? "#fff" : null });            // JPG는 투명 배경을 흰색으로
    const blob = await c.convertToBlob({ type: IMG_MIME[fmt], quality: fmt === "png" ? undefined : 0.92 });
    if (blob.type !== IMG_MIME[fmt]) throw new Error(`이 브라우저는 ${fmt.toUpperCase()} 저장을 지원하지 않아요`);
    outs.push({ blob, name: f.name.replace(/\.[^.]+$/, "") + "." + fmt });
  }
  progress(items.length, items.length, "사진 바꾸는 중…");
  if (outs.length <= 3) outs.forEach((o) => deliver(o.blob, o.name));
  else {
    const z = new JSZip();
    const used = new Set();
    for (const o of outs) { let n = o.name, k = 1; while (used.has(n)) n = o.name.replace(/(\.\w+)$/, ` (${k++})$1`); used.add(n); z.file(n, o.blob); }
    deliver(await z.generateAsync({ type: "blob" }), `사진_${fmt}.zip`);
  }
  return outs.length;
}

// ───────── ② PDF → 이미지 ─────────
async function pdfPages(file, scale = 150 / 72) {
  const pdf = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
  const pages = [];
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const vp = page.getViewport({ scale });
    const c = new OffscreenCanvas(Math.ceil(vp.width), Math.ceil(vp.height));
    const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height);
    await page.render({ canvasContext: g, viewport: vp }).promise;
    pages.push(c);
  }
  await pdf.destroy();
  return pages;
}

async function split(items) {
  for (const f of items) {
    msg(`${f.name} 쪼개는 중…`);
    const pages = await pdfPages(f.file);
    const z = new JSZip();
    for (const [i, c] of pages.entries()) {
      progress(i + 1, pages.length, `${f.name} 페이지 저장 중…`);
      z.file(`page-${String(i + 1).padStart(3, "0")}.jpg`, await (await c.convertToBlob({ type: "image/jpeg", quality: 0.9 })).arrayBuffer());
    }
    deliver(await z.generateAsync({ type: "blob" }), f.name.replace(/\.pdf$/i, "") + "_pages.zip");
  }
}

// ───────── ③ 문서 변환 (가운데 단계는 HTML) ─────────
const esc = (s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
async function toHtml(file) {
  const e = ext(file.name);
  if (e === "docx") return (await mammoth.convertToHtml({ arrayBuffer: await file.arrayBuffer() })).value;
  const text = await file.text();
  if (e === "md" || e === "markdown") return marked.parse(text);
  if (e === "html" || e === "htm") { const d = new DOMParser().parseFromString(text, "text/html"); d.querySelectorAll("script,style").forEach((n) => n.remove()); return d.body.innerHTML; }
  return text.split(/\n{2,}/).map((p) => `<p>${esc(p).replace(/\n/g, "<br>")}</p>`).join("\n");
}
function toMarkdown(html) {
  const d = new DOMParser().parseFromString(html, "text/html");
  d.querySelectorAll("table").forEach((t) => {                 // 표 첫 줄을 제목 줄로 → 마크다운 표로 변환됨
    const first = t.rows[0];
    if (first && ![...first.cells].some((c) => c.tagName === "TH")) {
      [...first.cells].forEach((c) => { const th = d.createElement("th"); th.innerHTML = c.innerHTML; c.replaceWith(th); });
    }
    t.querySelectorAll("td p, th p").forEach((p) => p.replaceWith(...p.childNodes, " "));
  });
  const t = new TurndownService({ headingStyle: "atx", bulletListMarker: "-", codeBlockStyle: "fenced" });
  t.use(turndownPluginGfm.gfm);
  return t.turndown(d.body.innerHTML).replace(/[ \t]+\|/g, " |");
}

function htmlToText(html) {
  const d = new DOMParser().parseFromString(html, "text/html");
  const blocks = [];
  const walk = (n) => {
    for (const c of n.children) {
      if (/^(P|H[1-6]|LI|PRE|BLOCKQUOTE|TR)$/.test(c.tagName)) blocks.push((c.tagName === "LI" ? "- " : "") + (c.tagName === "TR" ? [...c.cells].map((x) => x.textContent.trim()).join("\t") : c.textContent.trim()));
      else walk(c);
    }
  };
  walk(d.body);
  return blocks.filter(Boolean).join("\n\n") + "\n";
}

function htmlToDocx(html, title) {
  const D = docx;
  const dom = new DOMParser().parseFromString(html, "text/html");
  const runs = (node, style = {}) => {
    const out = [];
    for (const c of node.childNodes) {
      if (c.nodeType === 3) { if (c.textContent) out.push(new D.TextRun({ text: c.textContent.replace(/\s+/g, " "), ...style })); continue; }
      if (c.nodeType !== 1) continue;
      const t = c.tagName;
      if (t === "BR") out.push(new D.TextRun({ text: "", break: 1 }));
      else if (t === "STRONG" || t === "B") out.push(...runs(c, { ...style, bold: true }));
      else if (t === "EM" || t === "I") out.push(...runs(c, { ...style, italics: true }));
      else if (t === "CODE") out.push(...runs(c, { ...style, font: "Consolas" }));
      else if (t === "A") out.push(...runs(c, { ...style, color: "2456E6", underline: {} }));
      else out.push(...runs(c, style));
    }
    return out;
  };
  const HL = [D.HeadingLevel.HEADING_1, D.HeadingLevel.HEADING_2, D.HeadingLevel.HEADING_3, D.HeadingLevel.HEADING_4, D.HeadingLevel.HEADING_5, D.HeadingLevel.HEADING_6];
  const blocks = [];
  const walk = (node, depth = 0) => {
    for (const c of node.children) {
      const t = c.tagName;
      if (/^H[1-6]$/.test(t)) blocks.push(new D.Paragraph({ heading: HL[+t[1] - 1], children: runs(c) }));
      else if (t === "P") blocks.push(new D.Paragraph({ children: runs(c), spacing: { after: 120 } }));
      else if (t === "UL" || t === "OL") {
        [...c.children].forEach((li, i) => {
          const sub = [...li.children].filter((x) => x.tagName === "UL" || x.tagName === "OL");
          const own = li.cloneNode(true); own.querySelectorAll("ul,ol").forEach((x) => x.remove());
          const kids = runs(own);
          blocks.push(t === "UL" ? new D.Paragraph({ bullet: { level: Math.min(depth, 8) }, children: kids })
                                 : new D.Paragraph({ indent: { left: 360 * (depth + 1) }, children: [new D.TextRun(`${i + 1}. `), ...kids] }));
          sub.forEach((s) => walk({ children: [s] }, depth + 1));
        });
      } else if (t === "PRE") blocks.push(...c.textContent.replace(/\n$/, "").split("\n").map((l) => new D.Paragraph({ children: [new D.TextRun({ text: l, font: "Consolas", size: 20 })] })));
      else if (t === "BLOCKQUOTE") blocks.push(new D.Paragraph({ indent: { left: 567 }, children: runs(c, { italics: true }) }));
      else if (t === "HR") blocks.push(new D.Paragraph({ thematicBreak: true, children: [] }));
      else if (t === "TABLE") {
        const rows = [...c.querySelectorAll("tr")].map((tr) => new D.TableRow({
          children: [...tr.cells].map((cell) => new D.TableCell({ children: [new D.Paragraph({ children: runs(cell, cell.tagName === "TH" ? { bold: true } : {}) })] })),
        }));
        if (rows.length) blocks.push(new D.Table({ rows, width: { size: 100, type: D.WidthType.PERCENTAGE } }), new D.Paragraph({ children: [] }));
      } else if (c.children.length) walk(c, depth);
      else if (c.textContent.trim()) blocks.push(new D.Paragraph({ children: runs(c) }));
    }
  };
  walk(dom.body);
  return D.Packer.toBlob(new D.Document({ title, styles: { default: { document: { run: { font: "맑은 고딕", size: 22 } } } }, sections: [{ children: blocks.length ? blocks : [new D.Paragraph("")] }] }));
}

async function htmlTo(html, target, title) {
  if (target === "html") return new Blob([`<!doctype html>\n<html lang="ko"><head><meta charset="utf-8"><title>${esc(title)}</title>\n<style>body{font-family:system-ui,"Malgun Gothic",sans-serif;max-width:46em;margin:2em auto;padding:0 1em;line-height:1.6}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}</style></head>\n<body>\n${html}\n</body></html>\n`], { type: "text/html" });
  if (target === "md") return new Blob([toMarkdown(html) + "\n"], { type: "text/markdown" });
  if (target === "txt") return new Blob([htmlToText(html)], { type: "text/plain" });
  if (target === "docx") return htmlToDocx(html, title);
  throw new Error(target + " 형식은 지원하지 않아요");
}

async function convert(items, target) {
  let done = 0; const errs = [];
  for (const f of items) {
    if (ext(f.name) === target) continue;
    try {
      msg(`${f.name} → ${target} 바꾸는 중…`);
      const base = f.name.replace(/\.[^.]+$/, "");
      const blob = (ext(f.name) === "md" || ext(f.name) === "markdown") && target === "md" ? f.file : await htmlTo(await toHtml(f.file), target, base);
      deliver(blob, `${base}.${target}`); done++;
    } catch (e) { errs.push(`${f.name}: ${e.message}`); }
  }
  if (!done) throw new Error(errs[0] || "바꿀 문서가 없어요");
  return { done, errs };
}

// ───────── ④ 글자 추출 (온라인) ─────────
async function relay(path, body, timeout = 120000) {
  const url = relayUrl();
  if (!url) throw new Error("AI가 연결되지 않았어요 (⚙ 설정)");
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), timeout);
  try {
    const r = await fetch(url + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctl.signal });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `서버 오류 (HTTP ${r.status})`);
    return data;
  } catch (e) {
    if (e.name === "AbortError") throw new Error("서버 응답이 너무 늦어요");
    if (e instanceof TypeError) throw new Error("AI에 연결할 수 없어요 (인터넷 확인)");
    throw e;
  } finally { clearTimeout(t); }
}

async function canvasB64(c, maxSide = 1568) {
  let { width: w, height: h } = c;
  if (Math.max(w, h) > maxSide) { const s = maxSide / Math.max(w, h); w = Math.round(w * s); h = Math.round(h * s); }
  const o = new OffscreenCanvas(w, h); o.getContext("2d").drawImage(c, 0, 0, w, h);
  return toB64(new Uint8Array(await (await o.convertToBlob({ type: "image/jpeg", quality: 0.85 })).arrayBuffer()));
}

async function ocr(items, target, outBase) {
  const jobs = [];
  for (const f of items) {
    if (f.kind === "pdf") (await pdfPages(f.file)).forEach((c, i) => jobs.push({ f, c, page: i + 1 }));
    else jobs.push({ f, c: await drawImage(f, { fill: "#fff" }), page: 1 });
  }
  const parts = []; let last = null;
  for (const [i, j] of jobs.entries()) {
    progress(i, jobs.length, "글자 뽑는 중…");
    const { text } = await relay("/ocr", { image: await canvasB64(j.c), media_type: "image/jpeg" });
    if (items.length > 1 && j.f !== last) parts.push(`## ${j.f.name}`);
    last = j.f;
    if (text) parts.push(text);
  }
  const md = parts.join("\n\n").trim();
  if (!md) throw new Error("글자를 찾지 못했어요");
  const blob = target === "md" ? new Blob([md + "\n"], { type: "text/markdown" }) : await htmlTo(marked.parse(md), target, outBase);
  return deliver(blob, `${outBase}.${target}`);
}

// ───────── 실행 공통 ─────────
const opts = () => ({ sort: $("#sort").value, quality: $("#quality").value, perPage: +$("#perPage").value });
const outName = (fallback = "묶음") => ($("#outName").value.trim() || fallback).replace(/[\\/:*?"<>|]/g, "_");
const pick = (k) => state.files.filter((f) => (Array.isArray(k) ? k.includes(f.kind) : f.kind === k));

async function run(label, fn) {
  if (state.busy) return;
  busy(true, label);
  try { const r = await fn(); busy(false); msg(typeof r === "string" ? r : "✓ 다 됐어요! 아래에서 다시 받을 수 있어요.", "ok"); }
  catch (e) { console.error(e); busy(false); msg("✗ " + (e.message || e), "err"); }
}

function ask(title, body, sub = "") {
  const d = $("#confirmDlg");
  $("#cfTitle").textContent = title; $("#cfBody").textContent = body; $("#cfSub").textContent = sub;
  d.returnValue = "";
  d.showModal();
  return new Promise((res) => d.addEventListener("close", () => res(d.returnValue === "yes"), { once: true }));
}
async function ocrConsent() {
  if (store.get("ocrOk")) return true;
  const ok = await ask("사진을 AI로 보낼게요", "글자를 읽으려고 사진·PDF 내용을 AI(Claude)로 보내요.\n주민번호 같은 개인정보가 있는 문서는 주의해주세요.", "처음 한 번만 물어봐요");
  if (ok) store.set("ocrOk", "1");
  return ok;
}

document.querySelectorAll("[data-bundle]").forEach((b) => (b.onclick = () => {
  const kind = b.dataset.bundle;
  run(`이미지를 ${b.textContent}로 묶는 중…`, async () => { await bundle(pick("image"), `${outName()}.${kind}`, opts()); return `✓ 이미지 ${pick("image").length}장을 ${kind.toUpperCase()}로 묶었어요.`; });
}));
document.querySelectorAll("[data-imgconv]").forEach((b) => (b.onclick = () => {
  const fmt = b.dataset.imgconv;
  run("사진 바꾸는 중…", async () => `✓ 사진 ${await convertImages(pick("image"), fmt)}장을 ${fmt.toUpperCase()}로 바꿨어요.`);
}));
document.querySelectorAll("#examples button").forEach((b) => (b.onclick = () => { $("#ask").value = b.textContent; $("#ask").focus(); }));
$("#convBtn").onclick = () => run("변환 중…", async () => {
  const { done, errs } = await convert(pick("doc"), $("#target").value);
  return errs.length ? `✓ ${done}개 변환 · 실패 ${errs.length}개: ${errs[0]}` : `✓ 문서 ${done}개를 바꿨어요.`;
});
$("#splitBtn").onclick = () => run("PDF 쪼개는 중…", async () => { await split(pick("pdf")); return "✓ 페이지별 이미지를 ZIP으로 만들었어요."; });
$("#ocrBtn").onclick = async () => {
  if (!(await ocrConsent())) return msg("취소했어요.");
  run("글자 뽑는 중…", () => ocr(pick(["image", "pdf"]), $("#ocrTarget").value, outName("글자추출") === "묶음" ? "글자추출" : outName("글자추출")));
};

// 말로 시키기
$("#askForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#ask").value.trim();
  if (!text || !state.files.length || state.busy) return;
  const names = state.files.map((f) => f.name);
  const online = state.aiOnline;
  busy(true, online ? "AI가 문장을 읽는 중…" : "문장 읽는 중…");
  let plan, who;
  try {
    try {
      if (!online) throw new Error("offline");
      const { plan: p } = await relay("/plan", { text, files: names }, 30000);
      plan = check(fixPlan(p, text, names), names, { online }); who = "AI가 이해한 내용";
    } catch {
      plan = check(rulesPlan(text, names, { online }), names, { online }); who = "문장에서 찾은 내용";
    }
  } catch (err) { busy(false); return msg("✗ " + err.message, "err"); }
  busy(false);
  if (!(await ask("이렇게 할까요?", describe(plan), who))) return msg("취소했어요.");
  const byName = (n) => state.files.find((f) => f.name === n);
  let items = plan.files.map(byName);
  if (plan.action === "bundle") {
    let sort = plan.sort || "name";
    if (sort === "name" && $("#sort").value === "none") { sort = "none"; items = state.files.filter((f) => items.includes(f)); }
    return run("묶는 중…", async () => { await bundle(items, plan.out, { sort, quality: plan.quality || "normal", perPage: +plan.per_page || 1 }); return `✓ ${plan.out} 완성!`; });
  }
  if (plan.action === "convert") return run("변환 중…", async () => { const { done } = await convert(items, plan.target); return `✓ 문서 ${done}개를 바꿨어요.`; });
  if (plan.action === "imgconv") return run("사진 바꾸는 중…", async () => `✓ 사진 ${await convertImages(items, plan.target)}장을 ${plan.target.toUpperCase()}로 바꿨어요.`);
  if (plan.action === "split") return run("PDF 쪼개는 중…", async () => { await split(items); return "✓ 페이지별 이미지를 ZIP으로 만들었어요."; });
  if (plan.action === "ocr") {
    if (!(await ocrConsent())) return msg("취소했어요.");
    return run("글자 뽑는 중…", () => ocr(items, plan.target, "글자추출"));
  }
});

// ───────── AI 연결 ─────────
async function checkAi() {
  const chip = $("#aiChip");
  const set = (text, cls, tip) => { chip.textContent = text; chip.className = "ai " + cls; chip.title = tip; };
  state.aiOnline = false;
  const url = relayUrl();
  if (!url) { set("AI 꺼짐", "", "AI 없이도 모든 버튼은 쓸 수 있어요. ⚙ 설정에서 AI를 연결하면 글로 시키기가 똑똑해지고 글자 뽑기를 쓸 수 있어요."); return refresh(); }
  set("AI 확인 중…", "", "");
  try {
    const r = await fetch(url + "/health", { signal: AbortSignal.timeout(5000) });
    state.aiOnline = !!(await r.json()).ai;
  } catch { /* 연결 실패 */ }
  if (state.aiOnline) set("AI 켜짐", "on", "글로 시키기와 글자 뽑기에 AI(Claude)를 써요.");
  else set("AI 연결 안 됨", "warn", "AI에 연결할 수 없어요. 인터넷이나 ⚙ 설정의 주소를 확인해주세요. 다른 기능은 그대로 쓸 수 있어요.");
  refresh();
}
$("#serverBtn").onclick = () => {
  const d = $("#serverDlg");
  $("#serverUrl").value = relayUrl();
  d.returnValue = ""; d.showModal();
  d.addEventListener("close", () => { if (d.returnValue === "yes") { store.set("relay", $("#serverUrl").value.trim()); checkAi(); } }, { once: true });
};

render();
checkAi();
window.__fconv = { state, addFiles };                       // 자동 테스트용
