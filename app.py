#!/usr/bin/env python3
"""
파일 변환기 - PC용 화면 프로그램
  실행: python app.py
  필요: pip install PySide6 pillow python-docx python-pptx pypdfium2 pdf2docx
"""
import os, sys, traceback
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot, QSize, QUrl, QTimer
from PySide6.QtGui import QFont, QIcon, QPixmap, QImageReader, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QListWidget, QListWidgetItem, QAbstractItemView,
    QPushButton, QLabel, QLineEdit, QComboBox, QSpinBox, QHBoxLayout, QVBoxLayout, QGridLayout,
    QFileDialog, QMessageBox, QFrame, QProgressBar, QStyle, QSizePolicy,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fconv, fai

DOC_EXT = {".md", ".docx", ".doc", ".html", ".htm", ".txt", ".odt", ".epub", ".rtf",
           ".pptx", ".ppt", ".xlsx", ".xls", ".pdf", ".hwp", ".rst", ".tex"}
OK_EXT = fconv.IMG_EXT | DOC_EXT
QUALITY = {"보통": (80, 2000), "용량 작게": (60, 1500), "고화질": (95, 0)}
SORT = {"목록 순서": "none", "파일명순": "name", "찍은 시간순": "time"}

STYLE = """
* { font-size: 13px; color: #1f2328; }
QMainWindow, #root { background: #f6f7f9; }
#card { background: #ffffff; border: 1px solid #e3e6ea; border-radius: 10px; }
#title { font-size: 18px; font-weight: 700; }
#section { font-size: 12px; font-weight: 700; color: #6b7280; letter-spacing: 0.5px; }
#hint { color: #8b929c; }
#chip { border-radius: 10px; padding: 3px 10px; font-size: 12px; }
QListWidget { background: #ffffff; border: 2px dashed #d5d9df; border-radius: 10px; padding: 6px; }
QListWidget[filled="true"] { border: 1px solid #e3e6ea; }
QListWidget::item { border-radius: 6px; padding: 4px; }
QListWidget::item:selected { background: #e8f0fe; color: #1f2328; }
QPushButton { background: #ffffff; border: 1px solid #d5d9df; border-radius: 7px; padding: 7px 12px; }
QPushButton:hover { background: #f0f2f5; }
QPushButton:disabled { color: #a0a6ae; background: #f6f7f9; }
QPushButton#primary { background: #2563eb; border: 1px solid #2563eb; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #1d4ed8; }
QPushButton#primary:disabled { background: #93b4f5; border-color: #93b4f5; }
QPushButton#quick { padding: 9px 4px; font-weight: 600; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: url(ARROW); width: 10px; height: 10px; }
QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #d5d9df; selection-background-color: #e8f0fe; selection-color: #1f2328; outline: 0; }
QLineEdit, QComboBox, QSpinBox { background: #ffffff; border: 1px solid #d5d9df; border-radius: 7px; padding: 6px 8px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #2563eb; }
QProgressBar { border: none; background: #e5e7eb; border-radius: 3px; max-height: 6px; }
QProgressBar::chunk { background: #2563eb; border-radius: 3px; }
#log { color: #374151; }
"""


# ───────── 백그라운드 작업 (화면 안 멈추게) ─────────
class Worker(QObject):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except (SystemExit, ValueError) as e:   # fconv·fai가 내는 친절한 오류
            self.failed.emit(str(e))
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")


class Job(QObject):
    """메인 스레드에 사는 받는 쪽 → 결과 처리가 항상 화면 스레드에서 실행됨"""
    def __init__(self, parent, on_done, on_fail):
        super().__init__(parent)
        self.on_done, self.on_fail = on_done, on_fail

    @Slot(object)
    def done(self, r):
        self.on_done(r)

    @Slot(str)
    def failed(self, m):
        self.on_fail(m)


# ───────── 파일 목록 (드래그&드롭 + 순서 바꾸기) ─────────
class FileList(QListWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setIconSize(QSize(44, 44))
        self.setSpacing(2)
        self.model().rowsMoved.connect(lambda *a: self.changed.emit())

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.count() == 0:
            from PySide6.QtGui import QPainter, QColor
            p = QPainter(self.viewport())
            p.setPen(QColor("#8b929c"))
            f = p.font(); f.setPointSize(11); p.setFont(f)
            p.drawText(self.viewport().rect(), Qt.AlignCenter,
                       "여기에 파일을 끌어다 놓으세요\n\n이미지 · 문서 · PDF\n(폴더째 넣어도 돼요)")

    def dragEnterEvent(self, e):
        e.acceptProposedAction() if e.mimeData().hasUrls() else super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        e.acceptProposedAction() if e.mimeData().hasUrls() else super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            self.add_paths([u.toLocalFile() for u in e.mimeData().urls()])
            e.acceptProposedAction()
        else:
            super().dropEvent(e)
            self.changed.emit()

    def paths(self):
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())]

    def add_paths(self, paths):
        have = set(self.paths())
        expanded = []
        for p in paths:
            p = Path(p)
            if p.is_dir():
                expanded += sorted((c for c in p.iterdir() if c.is_file()), key=fconv.natural_key)
            elif p.is_file():
                expanded.append(p)
        for p in expanded:
            if p.suffix.lower() not in OK_EXT or str(p) in have:
                continue
            have.add(str(p))
            it = QListWidgetItem(self._icon(p), p.name)
            it.setData(Qt.UserRole, str(p))
            it.setToolTip(str(p))
            self.addItem(it)
        self.changed.emit()

    def _icon(self, p):
        if p.suffix.lower() in fconv.IMG_EXT:
            r = QImageReader(str(p))
            r.setAutoTransform(True)                       # 썸네일도 회전 보정
            s = r.size()
            if s.isValid():
                s.scale(88, 88, Qt.KeepAspectRatio)
                r.setScaledSize(s)
                img = r.read()
                if not img.isNull():
                    return QIcon(QPixmap.fromImage(img))
        sp = QStyle.SP_FileDialogDetailedView if p.suffix.lower() == ".pdf" else QStyle.SP_FileIcon
        return self.style().standardIcon(sp)

    def remove_selected(self):
        for it in self.selectedItems():
            self.takeItem(self.row(it))
        self.changed.emit()


# ───────── 메인 창 ─────────
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("파일 변환기")
        self.resize(980, 640)
        self.out_dir = None          # None이면 첫 파일 폴더
        self.last_out = None
        self.jobs = []
        self.models = None

        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)

        # 상단 바
        top = QHBoxLayout()
        top.addWidget(QLabel("파일 변환기", objectName="title"))
        top.addStretch()
        self.ai_chip = QLabel("AI 확인 중…", objectName="chip")
        self.model_box = QComboBox()
        self.model_box.setMinimumWidth(150)
        self.model_box.setVisible(False)
        refresh = QPushButton("↻")
        refresh.setFixedWidth(34)
        refresh.setToolTip("AI 연결 다시 확인")
        refresh.clicked.connect(self.check_ai)
        top.addWidget(self.ai_chip)
        top.addWidget(self.model_box)
        top.addWidget(refresh)
        outer.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(14)
        outer.addLayout(body, 1)

        # 왼쪽: 파일 목록
        left = QVBoxLayout()
        self.files = FileList()
        self.files.changed.connect(self.on_files_changed)
        left.addWidget(self.files, 1)
        row = QHBoxLayout()
        b_add = QPushButton("+ 파일 추가"); b_add.clicked.connect(self.pick_files)
        b_del = QPushButton("선택 삭제"); b_del.clicked.connect(self.files.remove_selected)
        b_clr = QPushButton("비우기"); b_clr.clicked.connect(lambda: (self.files.clear(), self.on_files_changed()))
        self.count_lbl = QLabel("", objectName="hint")
        for w in (b_add, b_del, b_clr):
            row.addWidget(w)
        row.addStretch()
        row.addWidget(self.count_lbl)
        left.addLayout(row)
        body.addLayout(left, 3)
        QShortcut(QKeySequence.Delete, self.files, activated=self.files.remove_selected)

        # 오른쪽: 작업 패널
        panel = QFrame(objectName="card")
        panel.setFixedWidth(360)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(16, 14, 16, 14)
        pv.setSpacing(8)
        body.addWidget(panel)

        pv.addWidget(QLabel("말로 시키기", objectName="section"))
        ask_row = QHBoxLayout()
        self.ask = QLineEdit()
        self.ask.setPlaceholderText("예: 사진 시간순으로 PDF로 묶어줘")
        self.ask.returnPressed.connect(self.run_ask)
        self.ask_btn = QPushButton("실행", objectName="primary")
        self.ask_btn.clicked.connect(self.run_ask)
        ask_row.addWidget(self.ask, 1)
        ask_row.addWidget(self.ask_btn)
        pv.addLayout(ask_row)

        pv.addSpacing(8)
        pv.addWidget(QLabel("이미지 묶기", objectName="section"))
        g = QGridLayout(); g.setSpacing(6)
        self.quick_btns = []
        for i, (label, ext) in enumerate([("PDF", "pdf"), ("Word", "docx"), ("PPT", "pptx"), ("ZIP", "zip")]):
            b = QPushButton(label, objectName="quick")
            b.clicked.connect(lambda _=False, e=ext: self.run_bundle(e))
            g.addWidget(b, 0, i)
            self.quick_btns.append(b)
        pv.addLayout(g)

        pv.addSpacing(8)
        pv.addWidget(QLabel("문서 변환 · PDF 쪼개기", objectName="section"))
        cr = QHBoxLayout()
        self.target = QComboBox()
        self.target.addItems(["docx (Word)", "pdf", "md", "html", "txt", "odt", "epub"])
        self.conv_btn = QPushButton("변환")
        self.conv_btn.clicked.connect(self.run_convert)
        self.split_btn = QPushButton("PDF → 이미지")
        self.split_btn.clicked.connect(self.run_split)
        cr.addWidget(self.target, 1)
        cr.addWidget(self.conv_btn)
        cr.addWidget(self.split_btn)
        pv.addLayout(cr)

        pv.addSpacing(8)
        pv.addWidget(QLabel("옵션", objectName="section"))
        og = QGridLayout(); og.setHorizontalSpacing(8); og.setVerticalSpacing(6)
        self.sort = QComboBox(); self.sort.addItems(list(SORT))
        self.sort.setToolTip("목록 순서 = 왼쪽 목록에서 끌어서 바꾼 순서 그대로")
        self.quality = QComboBox(); self.quality.addItems(list(QUALITY))
        self.per_page = QComboBox(); self.per_page.addItems([f"{i} 장" for i in range(1, 7)])
        self.name = QLineEdit("묶음")
        for r, (lbl, w) in enumerate([("순서", self.sort), ("화질", self.quality),
                                      ("Word 한 쪽에", self.per_page), ("결과 이름", self.name)]):
            og.addWidget(QLabel(lbl), r, 0)
            og.addWidget(w, r, 1)
        og.setColumnStretch(1, 1)
        pv.addLayout(og)

        pv.addSpacing(8)
        pv.addWidget(QLabel("저장 위치", objectName="section"))
        sr = QHBoxLayout()
        self.out_lbl = QLabel("첫 번째 파일과 같은 폴더", objectName="hint")
        self.out_lbl.setWordWrap(True)
        self.out_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        ob = QPushButton("변경"); ob.clicked.connect(self.pick_out)
        sr.addWidget(self.out_lbl, 1)
        sr.addWidget(ob)
        pv.addLayout(sr)
        pv.addStretch()

        # 하단 상태
        bottom = QFrame(objectName="card")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(14, 8, 10, 8)
        sv = QVBoxLayout(); sv.setSpacing(4)
        self.log = QLabel("파일을 넣고 작업을 골라주세요.", objectName="log")
        self.log.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.bar = QProgressBar(); self.bar.setRange(0, 0); self.bar.setVisible(False); self.bar.setTextVisible(False)
        sv.addWidget(self.log)
        sv.addWidget(self.bar)
        bl.addLayout(sv, 1)
        self.open_btn = QPushButton("결과 폴더 열기")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.open_result)
        bl.addWidget(self.open_btn)
        outer.addWidget(bottom)

        self.on_files_changed()
        QTimer.singleShot(100, self.check_ai)

    # ── 공통 ──
    def status(self, text, kind="info"):
        color = {"info": "#374151", "ok": "#15803d", "err": "#b91c1c"}[kind]
        self.log.setStyleSheet(f"color: {color};")
        self.log.setText(text)

    def busy(self, on, text=""):
        for w in self.quick_btns + [self.ask_btn, self.conv_btn, self.split_btn]:
            w.setEnabled(not on)
        self.bar.setVisible(on)
        if on:
            self.status(text)
        else:
            self.on_files_changed()

    def background(self, fn, on_done, text):
        self.busy(True, text)
        th, wk = QThread(self), Worker(fn)
        job = Job(self, lambda r: (self.busy(False), on_done(r)),
                  lambda m: (self.busy(False), self.status("✗ " + m, "err")))
        wk.moveToThread(th)
        th.started.connect(wk.run)
        wk.done.connect(job.done)
        wk.failed.connect(job.failed)
        wk.done.connect(th.quit); wk.failed.connect(th.quit)
        th.finished.connect(lambda: (self.jobs.remove(rec), job.deleteLater(), th.deleteLater()))
        rec = (th, wk, job)
        self.jobs.append(rec)                      # 참조 유지 (중간에 사라지면 크래시)
        th.start()

    def out_folder(self, paths):
        return Path(self.out_dir) if self.out_dir else Path(paths[0]).parent

    def on_files_changed(self):
        paths = self.files.paths()
        n_img = sum(Path(p).suffix.lower() in fconv.IMG_EXT for p in paths)
        n_pdf = sum(Path(p).suffix.lower() == ".pdf" for p in paths)
        n_doc = len(paths) - n_img
        self.files.setProperty("filled", bool(paths))
        self.files.style().polish(self.files)
        self.count_lbl.setText(f"이미지 {n_img} · 문서 {n_doc}" if paths else "")
        if self.bar.isVisible():
            return
        for b in self.quick_btns:
            b.setEnabled(n_img > 0)
        self.conv_btn.setEnabled(len(paths) > 0)
        self.split_btn.setEnabled(n_pdf > 0)
        self.ask_btn.setEnabled(len(paths) > 0)

    def done_msg(self, out, extra=""):
        self.last_out = Path(out)
        self.open_btn.setEnabled(True)
        size = ""
        if self.last_out.is_file():
            size = f"  ({self.last_out.stat().st_size / 1024 / 1024:.2f}MB)"
        self.status(f"✓ 완료: {self.last_out.name}{size}{extra}", "ok")

    def opts(self):
        q, m = QUALITY[self.quality.currentText()]
        return dict(sort=SORT[self.sort.currentText()], quality=q, max_size=m, per_page=self.per_page.currentIndex() + 1)

    # ── 파일 고르기 ──
    def pick_files(self):
        exts = " ".join("*" + e for e in sorted(OK_EXT))
        fs, _ = QFileDialog.getOpenFileNames(self, "파일 추가", "", f"지원 파일 ({exts});;모든 파일 (*)")
        self.files.add_paths(fs)

    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "저장 위치")
        if d:
            self.out_dir = d
            self.out_lbl.setText(d)

    def open_result(self):
        if self.last_out:
            target = self.last_out if self.last_out.is_dir() else self.last_out.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    # ── 빠른 작업 ──
    def run_bundle(self, ext):
        imgs = [p for p in self.files.paths() if Path(p).suffix.lower() in fconv.IMG_EXT]
        o = self.opts()
        name = (self.name.text().strip() or "묶음").replace("/", "_").replace("\\", "_")
        out = self.out_folder(imgs) / f"{name}.{ext}"
        self.background(lambda: fconv.bundle(imgs, out, o["sort"], o["quality"], o["max_size"], o["per_page"], quiet=True),
                        lambda r: self.done_msg(r, f" · 이미지 {len(imgs)}장"),
                        f"이미지 {len(imgs)}장을 {ext.upper()}로 묶는 중…")

    def run_convert(self):
        tgt = self.target.currentText().split()[0]
        paths = self.files.paths()
        docs = [p for p in paths if Path(p).suffix.lower() not in fconv.IMG_EXT]
        # 문서가 있으면 문서만 변환 (사진은 '이미지 묶기'로). 사진만 있을 때만 사진을 하나씩 변환
        srcs = [p for p in (docs or paths) if Path(p).suffix.lower().lstrip(".") != tgt]
        if not srcs:
            return self.status(f"이미 전부 {tgt} 형식이에요.", "err")
        folder = self.out_folder(srcs)

        def job():
            outs, errs = [], []
            for s in srcs:
                try:
                    out = fconv.unique_path(folder / (Path(s).stem + "." + tgt))
                    outs.append(fconv.convert(s, tgt, out))
                except SystemExit as e:
                    errs.append(f"{Path(s).name}: {e}")
            if not outs:
                raise SystemExit(errs[0] if errs else "변환 실패")
            return outs, errs

        def ok(r):
            outs, errs = r
            self.done_msg(outs[-1], f" 외 {len(outs) - 1}개" if len(outs) > 1 else "")
            if errs:
                self.status(self.log.text() + f"   ·  실패 {len(errs)}개: {errs[0]}", "err")
        self.background(job, ok, f"{len(srcs)}개 파일을 {tgt}로 변환 중…")

    def run_split(self):
        pdfs = [p for p in self.files.paths() if Path(p).suffix.lower() == ".pdf"]
        folder = self.out_folder(pdfs)

        def job():
            last = None
            for p in pdfs:
                last = fconv.split(p, "jpg", 150, fconv.unique_path(folder / (Path(p).stem + "_pages")))
            return last
        self.background(job, lambda r: self.done_msg(r, " (폴더)"), f"PDF {len(pdfs)}개를 이미지로 쪼개는 중…")

    # ── 말로 시키기 ──
    def run_ask(self):
        text = self.ask.text().strip()
        paths = self.files.paths()
        if not text or not paths:
            return
        by_name = {Path(p).name: p for p in paths}
        names = list(by_name)
        model = self.model_box.currentText() if self.models else None

        def got_plan(r):
            plan, who = r
            plan_paths = [by_name[n] for n in plan["files"]]
            if plan["action"] == "bundle" and self.sort.currentText() == "목록 순서" and plan.get("sort", "name") == "name":
                # 사용자가 순서를 직접 정해놨으면 그 순서 존중
                plan["sort"] = "none"
                plan_paths = [p for p in paths if p in plan_paths]
            msg = f"[{who}] {fai.describe(plan)}\n\n진행할까요?"
            if QMessageBox.question(self, "작업 확인", msg) != QMessageBox.Yes:
                return self.status("취소했어요.")
            self.exec_plan(plan, plan_paths)

        self.background(lambda: fai.make_plan(text, names, model), got_plan,
                        "AI가 요청을 해석하는 중…" if model else "요청 해석 중…")

    def exec_plan(self, plan, paths):
        folder = self.out_folder(paths)
        a = plan["action"]
        if a == "bundle":
            out = folder / plan["out"]
            self.background(lambda: fconv.bundle(paths, out, plan.get("sort", "name"), int(plan.get("quality", 80)),
                                                 int(plan.get("max_size", 2000)), int(plan.get("per_page", 1)), quiet=True),
                            lambda r: self.done_msg(r, f" · 이미지 {len(paths)}장"), "묶는 중…")
        elif a == "convert":
            tgt = plan["target"]
            self.background(lambda: [fconv.convert(p, tgt, fconv.unique_path(folder / (Path(p).stem + "." + tgt)))
                                     for p in paths][-1],
                            lambda r: self.done_msg(r), "변환 중…")
        elif a == "split":
            fmt = plan.get("format", "jpg")
            self.background(lambda: [fconv.split(p, fmt, 150, fconv.unique_path(folder / (Path(p).stem + "_pages")))
                                     for p in paths][-1],
                            lambda r: self.done_msg(r, " (폴더)"), "쪼개는 중…")

    # ── AI 연결 ──
    def check_ai(self):
        self.models = fai.list_models()
        if self.models:
            cur = self.model_box.currentText()
            self.model_box.clear()
            self.model_box.addItems(self.models)
            pick = cur if cur in self.models else next(
                (m for m in self.models if "qwen" in m and "7b" in m), self.models[0])
            self.model_box.setCurrentText(pick)
            self.model_box.setVisible(True)
            self.ai_chip.setText("● AI 연결됨")
            self.ai_chip.setStyleSheet("background:#dcfce7; color:#166534;")
        else:
            self.model_box.setVisible(False)
            msg = "○ 규칙 모드" if self.models is None else "○ 모델 없음"
            self.ai_chip.setText(msg)
            self.ai_chip.setToolTip("Ollama가 꺼져 있거나 모델이 없어요. 간단한 요청은 규칙으로 처리해요.")
            self.ai_chip.setStyleSheet("background:#f3f4f6; color:#4b5563;")


def main():
    app = QApplication(sys.argv)
    f = QFont()
    f.setFamilies(["Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "sans-serif"])
    app.setFont(f)
    import tempfile
    arrow = Path(tempfile.gettempdir()) / "fconv_arrow.svg"
    arrow.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                     '<path d="M1 3l4 4 4-4" fill="none" stroke="#6b7280" stroke-width="1.6"/></svg>')
    app.setStyleSheet(STYLE.replace("ARROW", arrow.as_posix()))
    w = Main()
    w.show()
    if len(sys.argv) > 1:                       # 파일을 exe 아이콘에 끌어다 놓아도 열림
        w.files.add_paths(sys.argv[1:])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
