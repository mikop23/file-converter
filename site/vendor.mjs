// node_modules → vendor/ 로 사이트에 필요한 파일만 복사
import { copyFileSync, mkdirSync } from "node:fs";
const files = {
  "jszip/dist/jszip.min.js": "jszip.min.js",
  "jspdf/dist/jspdf.umd.min.js": "jspdf.umd.min.js",
  "pptxgenjs/dist/pptxgen.bundle.js": "pptxgen.bundle.js",
  "docx/build/index.umd.js": "docx.umd.js",
  "marked/marked.min.js": "marked.min.js",
  "turndown/lib/turndown.browser.umd.js": "turndown.js",
  "turndown-plugin-gfm/dist/turndown-plugin-gfm.js": "turndown-plugin-gfm.js",
  "mammoth/mammoth.browser.min.js": "mammoth.browser.min.js",
  "exifr/dist/lite.umd.js": "exifr.lite.umd.js",
  "pdfjs-dist/build/pdf.min.mjs": "pdf.min.mjs",
  "pdfjs-dist/build/pdf.worker.min.mjs": "pdf.worker.min.mjs",
};
mkdirSync("vendor", { recursive: true });
for (const [from, to] of Object.entries(files)) copyFileSync("node_modules/" + from, "vendor/" + to);
console.log("vendor 복사 완료:", Object.keys(files).length, "개");
