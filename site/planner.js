// 말 → 작업 계획.  PC 앱 fai.py의 규칙(hints / ask_rules / fix_plan / check)을 옮긴 것
export const IMG_EXT = ["jpg", "jpeg", "png", "webp", "bmp", "gif"];
export const DOC_EXT = ["md", "markdown", "html", "htm", "txt", "docx"];
const IMG_GLOBS = IMG_EXT.map((e) => "*." + e);

const FORMAT_WORDS = [
  ["파워포인트", "pptx"], ["피피티", "pptx"], ["pptx", "pptx"], ["ppt", "pptx"],
  ["워드", "docx"], ["word", "docx"], ["docx", "docx"],
  ["압축파일", "zip"], ["압축 파일", "zip"], ["집파일", "zip"], ["zip", "zip"],
  ["피디에프", "pdf"], ["pdf", "pdf"],
  ["제이피지", "jpg"], ["제이펙", "jpg"], ["jpeg", "jpg"], ["jpg", "jpg"], ["피엔지", "png"], ["png", "png"], ["웹피", "webp"], ["webp", "webp"],
  ["마크다운", "md"], ["텍스트", "txt"], ["메모장", "txt"], ["txt", "txt"], ["html", "html"], ["웹페이지", "html"],
];
const SPLIT_WORDS = ["쪼개", "나눠", "나누", "분리", "페이지별", "장별"];
const OCR_WORDS = ["글자", "텍스트로", "타이핑", "ocr", "받아적", "받아 적", "글씨"];
const IMG_FMT = ["jpg", "png", "webp"];
const BUNDLE_WORDS = ["묶", "합쳐", "합치", "모아", "하나로"];

export const ext = (name) => (name.match(/\.([^.]+)$/)?.[1] || "").toLowerCase();
const stem = (name) => name.replace(/\.[^.]+$/, "");
const isImg = (n) => IMG_EXT.includes(ext(n));
const isPdf = (n) => ext(n) === "pdf";
const glob = (p) => new RegExp("^" + p.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".") + "$", "i");

function named(text, files) {
  const t = text.toLowerCase();
  return files.filter((f) => t.includes(f.toLowerCase()) || (stem(f).length >= 2 && t.includes(stem(f).toLowerCase())));
}

export function hints(text, files) {
  let t = text.toLowerCase();
  for (const f of files) t = t.split(f.toLowerCase()).join(" ").split(stem(f).toLowerCase()).join(" ");
  let fmt = null, pos = -1;
  for (const [word, e] of FORMAT_WORDS) {               // 문장에서 가장 뒤에 나온 형식 = 목표 형식
    const i = t.lastIndexOf(word);
    if (i > pos) { fmt = e; pos = i; }
  }
  const n = t.match(/(\d+)\s*장\s*씩|페이지[당에]?\s*(\d+)\s*장|한\s*(?:쪽|장|페이지)에\s*(\d+)/);
  return {
    fmt,
    split: SPLIT_WORDS.some((w) => t.includes(w)),
    ocr: OCR_WORDS.some((w) => t.includes(w)),
    bundle: BUNDLE_WORDS.some((w) => t.includes(w)),
    perPage: n ? Number(n[1] || n[2] || n[3]) : null,
    time: ["시간", "찍은", "날짜", "촬영"].some((w) => t.includes(w)),
    small: ["용량", "작게", "가볍", "압축해서"].some((w) => t.includes(w)),
    hq: ["고화질", "원본", "화질 좋"].some((w) => t.includes(w)),
  };
}

export function rulesPlan(text, files, { online = false } = {}) {
  const h = hints(text, files);
  const nm = named(text, files);
  if (online && h.ocr) {
    return { action: "ocr", files: nm.length ? nm : files.filter((f) => isImg(f) || isPdf(f)),
             target: ["txt", "md"].includes(h.fmt) ? h.fmt : "docx" };
  }
  const nmImg = nm.filter(isImg), nmPdf = nm.filter(isPdf);
  const saysPdf = /pdf|피디에프/i.test(text);
  if (IMG_FMT.includes(h.fmt) && files.some(isPdf) && (nmPdf.length || saysPdf || !files.some(isImg))) {   // "PDF를 jpg로" → 쪼개기
    return { action: "split", files: nmPdf.length ? nmPdf : files.filter(isPdf).slice(0, 1), format: "jpg" };
  }
  if (IMG_FMT.includes(h.fmt) && files.some(isImg) && !h.bundle) {                                    // "사진 png로 바꿔"
    return { action: "imgconv", files: nmImg.length ? nmImg : IMG_GLOBS, target: h.fmt };
  }
  if (h.split && files.some(isPdf)) {
    return { action: "split", files: nm.filter(isPdf).length ? nm.filter(isPdf) : files.filter(isPdf).slice(0, 1), format: "jpg" };
  }
  if (h.bundle || (!nm.some((f) => !isImg(f)) && ["pdf", "pptx", "docx", "zip"].includes(h.fmt) && files.some(isImg))) {
    return fixPlan({ action: "bundle", files: nm.filter(isImg).length ? nm.filter(isImg) : IMG_GLOBS, out: `묶음.${h.fmt || "pdf"}` }, text, files);
  }
  if (nm.length && h.fmt) return { action: "convert", files: nm, target: h.fmt };
  return { action: "unknown", reason: "파일 이름이나 원하는 형식을 같이 말해주세요" };
}

export function fixPlan(plan, text, files) {
  const h = hints(text, files);
  if (plan.action === "split" && !h.split) {
    plan.action = files.some(isImg) && [null, "pdf", "docx", "pptx", "zip"].includes(h.fmt) ? "bundle" : "convert";
    if (plan.action === "bundle") plan.files = IMG_GLOBS;
  }
  if (plan.action === "bundle") {
    const fl = plan.files || [];
    if (!fl.length || fl.every((f) => /[*?]/.test(f))) plan.files = IMG_GLOBS;
    if (!h.time && plan.sort === "time") plan.sort = "name";
    if (["pdf", "docx", "pptx", "zip"].includes(h.fmt)) plan.out = stem(plan.out || "묶음") + "." + h.fmt;
    if (h.perPage) plan.per_page = h.perPage;
    if (h.time) plan.sort = "time";
    if (h.small) plan.quality = "small";
    if (h.hq) plan.quality = "hq";
  } else if ((plan.action === "convert" || plan.action === "imgconv") && IMG_FMT.includes(h.fmt) && files.some(isImg)) {
    plan.action = "imgconv"; plan.target = h.fmt;
    if (!(plan.files || []).some((f) => isImg(f) || /[*?]/.test(f))) plan.files = IMG_GLOBS;
  } else if (plan.action === "convert" && h.fmt) {
    plan.target = h.fmt;
  } else if (plan.action === "ocr" && ["docx", "txt", "md"].includes(h.fmt)) {
    plan.target = h.fmt;
  }
  return plan;
}

/** 계획 검사: 목록에 없는 파일·이상한 형식 거르기. 문제 있으면 Error */
export function check(plan, files, { online = false } = {}) {
  const ok = ["bundle", "convert", "split", "imgconv", ...(online ? ["ocr"] : [])];
  if (!ok.includes(plan.action)) throw new Error(plan.reason || "처리할 수 없는 요청이에요");
  const real = [];
  for (const p of plan.files || []) {
    for (const f of /[*?]/.test(p) ? files.filter((f) => glob(p).test(f)) : files.filter((f) => f === p)) {
      if (!real.includes(f)) real.push(f);
    }
  }
  if (!real.length) throw new Error("해당하는 파일이 없어요");
  plan.files = real;
  if (plan.action === "bundle") {
    plan.files = real.filter(isImg);
    let out = String(plan.out || "묶음.pdf").split(/[\\/]/).pop();
    if (!["pdf", "docx", "pptx", "zip"].includes(ext(out))) out = stem(out) + ".pdf";
    plan.out = out;
    if (!plan.files.length) throw new Error("묶을 이미지가 없어요");
  }
  if (plan.action === "convert") {
    plan.target = String(plan.target || "").toLowerCase().replace(/^\./, "");
    if (plan.target === "pdf") throw new Error("PDF로 바꾸기는 PC 프로그램에서 할 수 있어요");
    if (!["docx", "md", "html", "txt"].includes(plan.target)) throw new Error(`${plan.target} 형식은 사이트에서 지원하지 않아요`);
    plan.files = real.filter((f) => DOC_EXT.includes(ext(f)) && ext(f) !== plan.target);
    if (!plan.files.length) throw new Error("바꿀 문서가 없어요 (md·html·txt·docx만 가능)");
  }
  if (plan.action === "imgconv") {
    plan.target = String(plan.target || "").toLowerCase().replace("jpeg", "jpg");
    if (!IMG_FMT.includes(plan.target)) throw new Error("사진은 JPG·PNG·WEBP로 바꿀 수 있어요");
    plan.files = real.filter((f) => isImg(f) && ext(f).replace("jpeg", "jpg") !== plan.target);
    if (!plan.files.length) throw new Error(`이미 전부 ${plan.target.toUpperCase()}예요`);
  }
  if (plan.action === "split") {
    plan.files = real.filter(isPdf);
    if (!plan.files.length) throw new Error("쪼갤 PDF가 없어요");
  }
  if (plan.action === "ocr") {
    plan.files = real.filter((f) => isImg(f) || isPdf(f));
    if (!["docx", "txt", "md"].includes(plan.target)) plan.target = "docx";
    if (!plan.files.length) throw new Error("글자를 뽑을 사진이나 PDF가 없어요");
  }
  return plan;
}

export function describe(p) {
  const n = p.files.length;
  const head = p.files.slice(0, 3).join(", ") + (n > 3 ? ` 외 ${n - 3}개` : "");
  if (p.action === "bundle") {
    const extra = [];
    if (p.sort === "time") extra.push("찍은 시간순");
    if ((p.per_page || 1) > 1) extra.push(`한 쪽에 ${p.per_page}장`);
    if (p.quality === "small") extra.push("용량 작게");
    if (p.quality === "hq") extra.push("고화질");
    return `사진 ${n}장 (${head})\n→ ${p.out} 한 파일로 합치기` + (extra.length ? `\n[${extra.join(", ")}]` : "");
  }
  if (p.action === "convert") return `문서 ${n}개 (${head})\n→ ${{ docx: "Word 문서", md: "마크다운", html: "웹페이지", txt: "텍스트" }[p.target] || p.target}로 바꾸기`;
  if (p.action === "imgconv") return `사진 ${n}장 (${head})\n→ ${p.target.toUpperCase()}로 바꾸기` + (n > 3 ? " (ZIP 하나로)" : "");
  if (p.action === "ocr") return `${head}\n→ 글자를 뽑아서 ${{ docx: "Word 문서", txt: "텍스트", md: "마크다운" }[p.target]}로 (AI로 전송)`;
  return `${head}\n→ 페이지별 사진 (ZIP)`;
}
