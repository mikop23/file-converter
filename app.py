#!/usr/bin/env python3
"""
파일 변환기 - PC용 화면 프로그램 (사이트와 같은 구성: 1 파일 넣기 → 2 할 일 고르기 → 3 받기)
  실행: python app.py
  필요: pip install PySide6 pillow python-docx python-pptx pypdfium2 pdf2docx
"""
import os, sys, traceback
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot, QSize, QUrl, QTimer
from PySide6.QtGui import QFont, QIcon, QPixmap, QImageReader, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QListWidget, QListWidgetItem, QAbstractItemView,
    QPushButton, QLabel, QLineEdit, QComboBox, QHBoxLayout, QVBoxLayout, QGridLayout,
    QFileDialog, QMessageBox, QFrame, QProgressBar, QStyle, QSizePolicy, QScrollArea, QDialog,
    QDialogButtonBox, QLayout,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fconv, fai, localai, relay

ONLINE = relay.edition() == "online"

DOC_EXT = {".md", ".docx", ".doc", ".html", ".htm", ".txt", ".odt", ".epub", ".rtf",
           ".pptx", ".ppt", ".xlsx", ".xls", ".pdf", ".hwp", ".rst", ".tex"}
OK_EXT = fconv.IMG_EXT | DOC_EXT
SORT = [("목록에 보이는 순서", "none"), ("파일 이름순", "name"), ("사진 찍은 시간순", "time")]
QUALITY = [("보통 (추천)", 80, 2000), ("용량 작게", 60, 1500), ("원본 화질", 95, 0)]
DOC_TARGETS = [("Word 문서 (.docx)", "docx"), ("PDF (.pdf)", "pdf"), ("마크다운 (.md)", "md"),
               ("웹페이지 (.html)", "html"), ("텍스트 (.txt)", "txt"), ("ODT 문서 (.odt)", "odt"),
               ("전자책 (.epub)", "epub")]
OCR_TARGETS = [("Word 문서 (.docx)", "docx"), ("텍스트 (.txt)", "txt"), ("마크다운 (.md)", "md")]
EXAMPLES = ["사진 PDF로 합쳐줘", "사진 png로 바꿔줘", "문서 워드로 바꿔줘", "PDF 사진으로 쪼개줘"]

# 사이트와 같은 색 (index.html의 :root 토큰)
STYLE = """
* { font-size: 13.5px; color: #1b2230; }
QMainWindow, #root, #tasks { background: #f3f5f8; }
QScrollArea { border: none; background: transparent; }
#title { font-size: 20px; font-weight: 750; }
#sub, #desc, #hint, #count { color: #667085; }
#desc, #why, #hint { font-size: 12.5px; }
#why { color: #667085; }
#step { font-size: 14.5px; font-weight: 700; }
#stepnum { background: #1b2230; color: #f3f5f8; border-radius: 11px; font-size: 12px; font-weight: 700;
           min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; qproperty-alignment: AlignCenter; }
#stepsub { color: #667085; font-size: 12.5px; }
#card, #status { background: #ffffff; border: 1px solid #dde2ea; border-radius: 12px; }
#card[off="true"] { background: transparent; border: 1px dashed #c4ccd8; }
#cardtitle { font-size: 15px; font-weight: 700; }
#card[off="true"] #cardtitle, #card[off="true"] #desc { color: #8a93a3; }
#badge { background: #e7eeff; color: #2456e6; border-radius: 8px; padding: 1px 7px; font-size: 11px; font-weight: 650; }
#ai { border-radius: 11px; padding: 4px 11px; font-size: 12.5px; background: #dde2ea; color: #667085; }
#ai[state="on"] { background: #dcf5e4; color: #157f3d; }
#ai[state="warn"] { background: #fde7e5; color: #b42318; }
QListWidget { background: #ffffff; border: 2px dashed #c4ccd8; border-radius: 12px; padding: 6px; }
QListWidget[filled="true"] { border: 1px solid #dde2ea; }
QListWidget::item { border-radius: 7px; padding: 4px; }
QListWidget::item:selected { background: #e7eeff; color: #1b2230; }
QListWidget#results { border: none; padding: 0; background: transparent; }
QListWidget#results::item { background: #dcf5e4; color: #157f3d; border-radius: 8px; padding: 5px 8px; margin: 2px 0; }
QPushButton { background: #ffffff; border: 1px solid #c4ccd8; border-radius: 9px; padding: 8px 12px; font-weight: 600; }
QPushButton:hover { border-color: #2456e6; color: #2456e6; }
QPushButton:disabled { color: #a6aebb; background: #f3f5f8; border-color: #dde2ea; }
QPushButton#primary { background: #2456e6; border: 1px solid #2456e6; color: white; }
QPushButton#primary:hover { background: #1f4bd0; color: white; }
QPushButton#primary:disabled { background: #9db4f3; border-color: #9db4f3; color: white; }
QPushButton#ghost { border-color: transparent; background: transparent; font-weight: 500; }
QPushButton#ghost:hover { color: #2456e6; }
QPushButton#example { border: 1px solid #dde2ea; background: #f3f5f8; border-radius: 12px; padding: 3px 10px;
                      font-weight: 500; font-size: 12.5px; color: #667085; }
QPushButton#example:hover { color: #2456e6; border-color: #2456e6; }
QPushButton#more { border: none; background: transparent; color: #667085; font-weight: 500; text-align: left; padding: 2px 0; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: url(ARROW); width: 10px; height: 10px; }
QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #c4ccd8; selection-background-color: #e7eeff; selection-color: #1b2230; outline: 0; }
QLineEdit, QComboBox { background: #ffffff; border: 1px solid #c4ccd8; border-radius: 9px; padding: 7px 10px; }
QLineEdit:focus, QComboBox:focus { border-color: #2456e6; }
QProgressBar { border: none; background: #dde2ea; border-radius: 2px; max-height: 4px; }
QProgressBar::chunk { background: #2456e6; border-radius: 2px; }
"""


# ───────── 백그라운드 작업 (화면 안 멈추게) ─────────
class Worker(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float, float)

    def __init__(self, fn, with_progress=False):
        super().__init__()
        self.fn, self.with_progress = fn, with_progress

    def run(self):
        try:
            self.done.emit(self.fn(self.progress.emit) if self.with_progress else self.fn())
        except (SystemExit, ValueError, ConnectionError) as e:   # 친절한 오류 메시지
            self.failed.emit(str(e))
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")


class Job(QObject):
    """메인 스레드에 사는 받는 쪽 → 결과 처리가 항상 화면 스레드에서 실행됨"""
    def __init__(self, parent, on_done, on_fail, on_progress=None):
        super().__init__(parent)
        self.on_done, self.on_fail, self.on_progress = on_done, on_fail, on_progress

    @Slot(float, float)
    def progress(self, a, b):
        if self.on_progress:
            self.on_progress(a, b)

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
            r = self.viewport().rect()
            f = p.font(); f.setPointSize(12); f.setBold(True); p.setFont(f)
            p.setPen(QColor("#1b2230"))
            p.drawText(r.adjusted(0, -40, 0, -40), Qt.AlignCenter, "여기에 파일을 끌어다 놓으세요")
            f.setBold(False); f.setPointSize(10); p.setFont(f)
            p.setPen(QColor("#667085"))
            p.drawText(r.adjusted(0, 10, 0, 10), Qt.AlignCenter,
                       "또는 아래 '파일 고르기'를 누르세요 · 폴더째 넣어도 돼요\n\n"
                       "사진 jpg·png·webp   ·   PDF   ·   Word·PPT·엑셀·마크다운·웹페이지·텍스트")

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
            size = p.stat().st_size
            size = f"{size / 1048576:.1f}MB" if size > 1048576 else f"{max(1, size // 1024)}KB"
            it = QListWidgetItem(self._icon(p), f"{p.name}    ·  {size}")
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


# ───────── 화면 조각 ─────────
def label(text, name=None, wrap=False):
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    return l

def step(num, title, sub=""):
    row = QHBoxLayout(); row.setSpacing(8)
    row.addWidget(label(str(num), "stepnum"))
    row.addWidget(label(title, "step"))
    if sub:
        row.addWidget(label(sub, "stepsub"))
    row.addStretch()
    return row


class Card(QFrame):
    """제목 + 한 줄 설명 + 내용 + (못 쓸 때) 이유"""
    def __init__(self, title, desc, badge=None):
        super().__init__()
        self.setObjectName("card")
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(16, 13, 16, 13)
        self.box.setSpacing(8)
        head = QHBoxLayout(); head.setSpacing(6)
        head.addWidget(label(title, "cardtitle"))
        if badge:
            head.addWidget(label(badge, "badge"))
        head.addStretch()
        self.box.addLayout(head)
        self.box.addWidget(label(desc, "desc", wrap=True))
        self.why = label("", "why", wrap=True)
        self._why_added = False

    def add(self, w):
        (self.box.addLayout if isinstance(w, QLayout) else self.box.addWidget)(w)
        return w

    def finish(self):
        self.box.addWidget(self.why)

    def set_state(self, ok, why=""):
        self.setProperty("off", not ok)
        self.style().unpolish(self); self.style().polish(self)
        for w in self.findChildren(QLabel):
            w.style().unpolish(w); w.style().polish(w)
        self.why.setText(("ⓘ " + why) if why else "")
        self.why.setVisible(bool(why))


# ───────── 메인 창 ─────────
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("파일 변환기" + (" (온라인)" if ONLINE else ""))
        self.resize(1080, 760)
        self.out_dir = None          # None이면 원본 파일 폴더
        self.last_out = None
        self.jobs = []
        self.ai_mode = None          # None | "online" | "ollama" | "builtin"
        self.server = localai.Server()
        self.models = None
        self.starting = False

        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(14)

        # ── 맨 위 ──
        top = QHBoxLayout()
        brand = QVBoxLayout(); brand.setSpacing(0)
        brand.addWidget(label("파일 변환기", "title"))
        brand.addWidget(label("사진·문서·PDF를 원하는 형식으로. " +
                              ("AI를 쓸 때만 인터넷을 써요." if ONLINE else "모든 작업이 이 PC 안에서 끝나요."), "sub"))
        top.addLayout(brand)
        top.addStretch()
        self.ai_chip = label("AI 확인 중…", "ai")
        self.get_ai_btn = QPushButton(f"AI 켜기 ({localai.MODEL_SIZE_MB / 1000:.1f}GB 받기)")
        self.get_ai_btn.setVisible(False)
        self.get_ai_btn.clicked.connect(self.get_ai)
        settings = QPushButton("⚙ 설정", objectName="ghost")
        settings.clicked.connect(self.open_settings)
        self.ai_chip.setFixedHeight(26)
        for wdg in (self.ai_chip, self.get_ai_btn, settings):
            top.addWidget(wdg, 0, Qt.AlignVCenter)
        outer.addLayout(top)

        body = QHBoxLayout(); body.setSpacing(16)
        outer.addLayout(body, 1)

        # ── 1 파일 넣기 ──
        left = QVBoxLayout(); left.setSpacing(8)
        left.addLayout(step(1, "파일 넣기"))
        self.files = FileList()
        self.files.changed.connect(self.on_files_changed)
        left.addWidget(self.files, 1)
        row = QHBoxLayout()
        b_add = QPushButton("+ 파일 고르기", objectName="primary"); b_add.clicked.connect(self.pick_files)
        b_del = QPushButton("고른 것 빼기", objectName="ghost"); b_del.clicked.connect(self.files.remove_selected)
        b_clr = QPushButton("모두 빼기", objectName="ghost")
        b_clr.clicked.connect(lambda: (self.files.clear(), self.on_files_changed()))
        self.count_lbl = label("", "count")
        for w in (b_add, b_del, b_clr):
            row.addWidget(w)
        row.addStretch()
        row.addWidget(self.count_lbl)
        left.addLayout(row)
        self.tray_tip = label("줄을 끌어서 순서를 바꿀 수 있어요. 사진을 합칠 때 이 순서대로 들어가요.", "hint", wrap=True)
        left.addWidget(self.tray_tip)
        body.addLayout(left, 1)
        QShortcut(QKeySequence.Delete, self.files, activated=self.files.remove_selected)

        # ── 2 할 일 고르기 (카드) ──
        right = QVBoxLayout(); right.setSpacing(8)
        right.addLayout(step(2, "할 일 고르기", "버튼만 누르면 바로 만들어져요"))
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tasks = QWidget(objectName="tasks")
        tv = QVBoxLayout(tasks); tv.setContentsMargins(0, 0, 6, 0); tv.setSpacing(10)
        scroll.setWidget(tasks)
        scroll.setFixedWidth(430)
        right.addWidget(scroll, 1)
        body.addLayout(right)

        # 글로 시키기
        self.c_ask = Card("글로 시키기", "하고 싶은 걸 문장으로 쓰면 알아서 골라서 해줘요.")
        ar = QHBoxLayout()
        self.ask = QLineEdit(); self.ask.setPlaceholderText("예: 사진 찍은 순서대로 PDF로 합쳐줘")
        self.ask.returnPressed.connect(self.run_ask)
        self.ask_btn = QPushButton("하기", objectName="primary"); self.ask_btn.clicked.connect(self.run_ask)
        ar.addWidget(self.ask, 1); ar.addWidget(self.ask_btn)
        self.c_ask.add(ar)
        eg = QGridLayout(); eg.setSpacing(6)
        for i, t in enumerate(EXAMPLES):
            b = QPushButton(t, objectName="example")
            b.clicked.connect(lambda _=False, t=t: (self.ask.setText(t), self.ask.setFocus()))
            eg.addWidget(b, i // 2, i % 2)
        self.c_ask.add(eg)
        self.c_ask.finish()
        tv.addWidget(self.c_ask)

        # 사진 한 파일로 합치기
        self.c_bundle = Card("사진 한 파일로 합치기", "여러 장의 사진을 PDF·Word·PPT·ZIP 하나로 만들어요.")
        bg = QGridLayout(); bg.setSpacing(6)
        self.bundle_btns = []
        for i, (lbl, ext) in enumerate([("PDF", "pdf"), ("Word", "docx"), ("PPT", "pptx"), ("ZIP", "zip")]):
            b = QPushButton(lbl); b.clicked.connect(lambda _=False, e=ext: self.run_bundle(e))
            bg.addWidget(b, 0, i); self.bundle_btns.append(b)
        self.c_bundle.add(bg)
        self.more_btn = QPushButton("▸ 순서 · 화질 · 파일 이름", objectName="more")
        self.more_btn.setCheckable(True)
        self.c_bundle.add(self.more_btn)
        self.opts_box = QWidget()
        og = QGridLayout(self.opts_box); og.setContentsMargins(0, 0, 0, 0); og.setHorizontalSpacing(10); og.setVerticalSpacing(6)
        self.sort = QComboBox(); self.sort.addItems([s for s, _ in SORT])
        self.quality = QComboBox(); self.quality.addItems([q[0] for q in QUALITY])
        self.per_page = QComboBox(); self.per_page.addItems([f"사진 {i}장" for i in (1, 2, 3, 4, 6)])
        self.name = QLineEdit("묶음")
        for r, (l, w) in enumerate([("순서", self.sort), ("화질", self.quality), ("Word 한 쪽에", self.per_page), ("파일 이름", self.name)]):
            og.addWidget(label(l), r, 0); og.addWidget(w, r, 1)
        og.setColumnStretch(1, 1)
        self.opts_box.setVisible(False)
        self.more_btn.toggled.connect(lambda on: (self.opts_box.setVisible(on),
                                                  self.more_btn.setText(("▾" if on else "▸") + " 순서 · 화질 · 파일 이름")))
        self.c_bundle.add(self.opts_box)
        self.c_bundle.finish()
        tv.addWidget(self.c_bundle)

        # 사진 형식 바꾸기
        self.c_img = Card("사진 형식 바꾸기", "사진마다 원하는 형식으로 바꿔요. 크기와 화질은 그대로예요.")
        ig = QGridLayout(); ig.setSpacing(6)
        self.imgconv_btns = []
        for i, f in enumerate(["jpg", "png", "webp"]):
            b = QPushButton(f.upper()); b.clicked.connect(lambda _=False, f=f: self.run_imgconv(f))
            ig.addWidget(b, 0, i); self.imgconv_btns.append(b)
        self.c_img.add(ig)
        self.c_img.finish()
        tv.addWidget(self.c_img)

        # 문서 형식 바꾸기
        self.c_doc = Card("문서 형식 바꾸기", "Word·PPT·엑셀·PDF·마크다운·웹페이지·텍스트를 다른 형식으로 바꿔요. "
                                            "Word↔PDF도 돼요.")
        dr = QHBoxLayout()
        self.target = QComboBox(); self.target.addItems([t for t, _ in DOC_TARGETS])
        self.conv_btn = QPushButton("바꾸기"); self.conv_btn.clicked.connect(self.run_convert)
        dr.addWidget(self.target, 1); dr.addWidget(self.conv_btn)
        self.c_doc.add(dr)
        self.c_doc.finish()
        tv.addWidget(self.c_doc)

        # PDF를 사진으로
        self.c_split = Card("PDF를 사진으로", "PDF 한 쪽 한 쪽을 사진(JPG)으로 바꿔서 폴더에 넣어줘요.")
        self.split_btn = QPushButton("페이지별 사진으로 바꾸기"); self.split_btn.clicked.connect(self.run_split)
        self.c_split.add(self.split_btn)
        self.c_split.finish()
        tv.addWidget(self.c_split)

        # 사진 속 글자 뽑기 (온라인 버전만)
        self.c_ocr = Card("사진 속 글자 뽑기", "사진이나 스캔한 PDF의 글자를 읽어서 문서로 만들어요.", badge="AI")
        orow = QHBoxLayout()
        self.ocr_target = QComboBox(); self.ocr_target.addItems([t for t, _ in OCR_TARGETS])
        self.ocr_btn = QPushButton("글자 뽑기"); self.ocr_btn.clicked.connect(lambda: self.run_ocr())
        orow.addWidget(self.ocr_target, 1); orow.addWidget(self.ocr_btn)
        self.c_ocr.add(orow)
        self.c_ocr.finish()
        self.c_ocr.setVisible(ONLINE)
        tv.addWidget(self.c_ocr)
        tv.addStretch()

        # ── 3 받기 ──
        status = QFrame(objectName="status")
        sv = QVBoxLayout(status); sv.setContentsMargins(16, 12, 16, 12); sv.setSpacing(8)
        sv.addLayout(step(3, "받기", "만든 파일은 아래 저장 위치에 저장돼요. 두 번 누르면 열려요"))
        self.log = label("파일을 넣고 할 일을 골라주세요.", "log", wrap=True)
        self.log.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sv.addWidget(self.log)
        self.bar = QProgressBar(); self.bar.setRange(0, 0); self.bar.setVisible(False); self.bar.setTextVisible(False)
        sv.addWidget(self.bar)
        self.results = QListWidget(objectName="results")
        self.results.setFlow(QListWidget.LeftToRight); self.results.setWrapping(True)
        self.results.setMaximumHeight(76); self.results.setVisible(False)
        self.results.setSpacing(3)
        self.results.itemDoubleClicked.connect(lambda it: QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(Qt.UserRole))))
        sv.addWidget(self.results)
        srow = QHBoxLayout()
        srow.addWidget(label("저장 위치:", "hint"))
        self.out_lbl = label("원본 파일과 같은 폴더", "hint")
        self.out_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        srow.addWidget(self.out_lbl, 1)
        ob = QPushButton("바꾸기", objectName="ghost"); ob.clicked.connect(self.pick_out)
        self.open_btn = QPushButton("결과 폴더 열기"); self.open_btn.setEnabled(False); self.open_btn.clicked.connect(self.open_result)
        srow.addWidget(ob); srow.addWidget(self.open_btn)
        sv.addLayout(srow)
        outer.addWidget(status)

        self.on_files_changed()
        QTimer.singleShot(100, self.check_ai)

    # ── 공통 ──
    def status(self, text, kind="info"):
        color = {"info": "#1b2230", "ok": "#157f3d", "err": "#b42318"}[kind]
        self.log.setStyleSheet(f"color: {color};")
        self.log.setText(text)

    def action_buttons(self):
        return self.bundle_btns + self.imgconv_btns + [self.ask_btn, self.conv_btn, self.split_btn, self.ocr_btn]

    def busy(self, on, text=""):
        for w in self.action_buttons():
            w.setEnabled(not on)
        self.bar.setRange(0, 0)
        self.bar.setVisible(on)
        if on:
            self.status(text)
        else:
            self.on_files_changed()

    def background(self, fn, on_done, text, on_fail=None, block=True, on_progress=None):
        """fn을 백그라운드에서 실행. block=False면 다른 작업 버튼을 막지 않음"""
        if block:
            self.busy(True, text)
        unblock = (lambda: self.busy(False)) if block else (lambda: None)
        th, wk = QThread(self), Worker(fn, on_progress is not None)
        job = Job(self, lambda r: (unblock(), on_done(r)),
                  lambda m: (unblock(), (on_fail or self.fail)(m)), on_progress)
        wk.moveToThread(th)
        th.started.connect(wk.run)
        wk.done.connect(job.done)
        wk.failed.connect(job.failed)
        wk.progress.connect(job.progress)
        wk.done.connect(th.quit); wk.failed.connect(th.quit)
        th.finished.connect(lambda: (self.jobs.remove(rec), job.deleteLater(), th.deleteLater()))
        rec = (th, wk, job)
        self.jobs.append(rec)                      # 참조 유지 (중간에 사라지면 크래시)
        th.start()

    def confirm(self, title, body, sub="", yes="진행"):
        """예/아니요 확인 창 (사이트의 확인 창과 같은 말투)"""
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(f"<b>{title}</b>")
        box.setInformativeText((f"<span style='color:#2456e6'>{sub}</span><br><br>" if sub else "")
                               + body.replace("\n", "<br>"))
        y = box.addButton(yes, QMessageBox.AcceptRole)
        box.addButton("취소", QMessageBox.RejectRole)
        box.setDefaultButton(y)
        box.exec()
        return box.clickedButton() is y

    def fail(self, m):
        if "NEED_OFFICE" in m:
            return self.offer_office()
        self.status("✗ " + m, "err")

    def offer_office(self):
        if not self.confirm("LibreOffice를 설치할까요?",
                            "Word·PPT·엑셀을 PDF로 바꾸려면 MS 오피스나 LibreOffice(무료)가 필요한데,\n"
                            "이 PC에서 둘 다 못 찾았어요.\n\n약 350MB이고 몇 분 걸려요.", yes="설치"):
            return self.status("Word·PPT·엑셀 → PDF는 MS 오피스나 LibreOffice가 있어야 해요.", "err")

        def ok(r):
            if r:
                self.status("✓ LibreOffice 설치가 끝났어요. '바꾸기'를 다시 눌러주세요.", "ok")
            else:
                self.status("✗ 자동 설치가 안 됐어요. libreoffice.org에서 직접 설치해주세요.", "err")
        self.background(fconv.install_libreoffice, ok, "LibreOffice 설치 중… (몇 분 걸려요, 창을 닫지 마세요)")

    def out_folder(self, paths):
        return Path(self.out_dir) if self.out_dir else Path(paths[0]).parent

    def kinds(self):
        paths = self.files.paths()
        img = [p for p in paths if Path(p).suffix.lower() in fconv.IMG_EXT]
        pdf = [p for p in paths if Path(p).suffix.lower() == ".pdf"]
        doc = [p for p in paths if Path(p).suffix.lower() not in fconv.IMG_EXT]   # PDF도 문서 변환 가능
        return paths, img, pdf, doc

    def on_files_changed(self):
        paths, img, pdf, doc = self.kinds()
        self.files.setProperty("filled", bool(paths))
        self.files.style().unpolish(self.files); self.files.style().polish(self.files)
        n_doc = len(doc) - len(pdf)
        self.count_lbl.setText(f"사진 {len(img)} · PDF {len(pdf)} · 문서 {n_doc}" if paths else "")
        self.tray_tip.setVisible(len(paths) >= 2)
        if self.bar.isVisible():
            return
        for b in self.bundle_btns + self.imgconv_btns:
            b.setEnabled(bool(img))
        self.conv_btn.setEnabled(bool(doc))
        self.split_btn.setEnabled(bool(pdf))
        self.ask_btn.setEnabled(bool(paths))
        self.c_bundle.set_state(bool(img), "" if img else "사진을 넣으면 쓸 수 있어요.")
        self.c_img.set_state(bool(img), "" if img else "사진을 넣으면 쓸 수 있어요.")
        self.c_doc.set_state(bool(doc), "" if doc else "문서나 PDF를 넣으면 쓸 수 있어요.")
        self.c_split.set_state(bool(pdf), "" if pdf else "PDF를 넣으면 쓸 수 있어요.")
        ai_on = self.ai_mode is not None
        self.c_ask.set_state(True, "AI가 켜져 있어서 자유롭게 써도 알아들어요." if ai_on
                             else "지금은 간단한 문장만 알아들어요. (형식 이름과 '합쳐줘·바꿔줘·쪼개줘' 같은 말)")
        ocr_ok = bool(img or pdf) and self.ai_mode == "online"
        self.ocr_btn.setEnabled(ocr_ok)
        self.c_ocr.set_state(ocr_ok, "사진 내용이 AI로 전송돼서 읽혀요." if ocr_ok
                             else "⚙ 설정에서 AI를 연결하면 쓸 수 있어요." if not relay.server_url()
                             else "AI에 연결이 안 돼요. 인터넷을 확인해주세요." if self.ai_mode != "online"
                             else "사진이나 PDF를 넣으면 쓸 수 있어요.")

    def done_msg(self, out, extra=""):
        outs = out if isinstance(out, list) else [out]
        outs = [Path(o) for o in outs if o]
        if not outs:
            return
        self.last_out = outs[-1]
        self.open_btn.setEnabled(True)
        for o in outs:
            size = ""
            if o.is_file():
                b = o.stat().st_size
                size = f"  {b / 1048576:.1f}MB" if b > 1048576 else f"  {max(1, b // 1024)}KB"
            it = QListWidgetItem(("📁 " if o.is_dir() else "↓ ") + o.name + size)
            it.setData(Qt.UserRole, str(o)); it.setToolTip(str(o))
            self.results.insertItem(0, it)
        self.results.setVisible(True)
        self.status(f"✓ 다 됐어요! {outs[-1].name}" + (f" 외 {len(outs) - 1}개" if len(outs) > 1 else "") + extra, "ok")

    def opts(self):
        _, q, m = QUALITY[self.quality.currentIndex()]
        return dict(sort=SORT[self.sort.currentIndex()][1], quality=q, max_size=m,
                    per_page=int(self.per_page.currentText().split()[1].rstrip("장")))

    # ── 파일 고르기 / 저장 위치 ──
    def pick_files(self):
        exts = " ".join("*" + e for e in sorted(OK_EXT))
        fs, _ = QFileDialog.getOpenFileNames(self, "파일 고르기", "", f"지원하는 파일 ({exts});;모든 파일 (*)")
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

    # ── 버튼 작업 ──
    def run_bundle(self, ext, paths=None, plan=None):
        _, img, _, _ = self.kinds()
        imgs = paths or img
        o = self.opts()
        if plan:
            o.update(sort=plan.get("sort", "name"), quality=int(plan.get("quality", 80)),
                     max_size=int(plan.get("max_size", 2000)), per_page=int(plan.get("per_page", 1)))
            out = self.out_folder(imgs) / plan["out"]
        else:
            name = (self.name.text().strip() or "묶음").replace("/", "_").replace("\\", "_")
            out = self.out_folder(imgs) / f"{name}.{ext}"
        self.background(lambda: fconv.bundle(imgs, out, o["sort"], o["quality"], o["max_size"], o["per_page"], quiet=True),
                        lambda r: self.done_msg(r, f" · 사진 {len(imgs)}장"),
                        f"사진 {len(imgs)}장을 {Path(out).suffix[1:].upper()} 한 파일로 합치는 중…")

    def run_imgconv(self, fmt, paths=None):
        _, img, _, _ = self.kinds()
        srcs = paths or img
        folder = self.out_folder(srcs)

        def job(progress):
            outs = []
            for i, s in enumerate(srcs, 1):
                outs.append(fconv.convert_image(s, fmt, folder / (Path(s).stem + "." + fmt)))
                progress(i, len(srcs))
            return outs

        def prog(done, total):
            self.bar.setRange(0, int(total)); self.bar.setValue(int(done))
            self.status(f"사진 바꾸는 중… {int(done)}/{int(total)}")
        self.background(job, lambda r: self.done_msg(r, f" · {fmt.upper()}로 바꿨어요"),
                        f"사진 {len(srcs)}장을 {fmt.upper()}로 바꾸는 중…", on_progress=prog)

    def run_convert(self, paths=None, tgt=None):
        tgt = tgt or DOC_TARGETS[self.target.currentIndex()][1]
        _, _, _, doc = self.kinds()
        srcs = [p for p in (paths or doc) if Path(p).suffix.lower().lstrip(".") != tgt]
        if not srcs:
            return self.status(f"이미 전부 {tgt} 형식이에요.", "err")
        folder = self.out_folder(srcs)

        def job():
            outs, errs = [], []
            for s in srcs:
                try:
                    outs.append(fconv.convert(s, tgt, fconv.unique_path(folder / (Path(s).stem + "." + tgt))))
                except SystemExit as e:
                    errs.append(f"{Path(s).name}: {e}")
            if not outs:
                raise SystemExit(errs[0] if errs else "바꾸지 못했어요")
            return outs, errs

        def ok(r):
            outs, errs = r
            self.done_msg(outs)
            if errs:
                if any("NEED_OFFICE" in e for e in errs):
                    return self.offer_office()
                self.status(self.log.text() + f"   ·  실패 {len(errs)}개: {errs[0]}", "err")
        self.background(job, ok, f"문서 {len(srcs)}개를 바꾸는 중…")

    def run_split(self, paths=None, fmt="jpg"):
        _, _, pdf, _ = self.kinds()
        pdfs = paths or pdf
        folder = self.out_folder(pdfs)
        self.background(lambda: [fconv.split(p, fmt, 150, fconv.unique_path(folder / (Path(p).stem + "_pages"))) for p in pdfs],
                        lambda r: self.done_msg(r, " (페이지별 사진 폴더)"), f"PDF {len(pdfs)}개를 사진으로 바꾸는 중…")

    def run_ocr(self, paths=None, target=None):
        _, img, pdf, _ = self.kinds()
        paths = paths or (img + pdf)
        target = target or OCR_TARGETS[self.ocr_target.currentIndex()][1]
        if not paths:
            return
        if not relay.load_config().get("ocr_ok"):
            if not self.confirm("사진을 AI로 보낼게요",
                                "글자를 읽으려고 사진·PDF 내용을 AI(Claude)로 보내요.\n"
                                "주민번호 같은 개인정보가 있는 문서는 주의해주세요.", sub="처음 한 번만 물어봐요"):
                return self.status("취소했어요.")
            relay.save_config(ocr_ok=True)
        name = (self.name.text().strip() or "묶음")
        out = self.out_folder(paths) / f"{'글자추출' if name == '묶음' else name}.{target}"

        def prog(done, total):
            self.bar.setRange(0, int(total)); self.bar.setValue(int(done))
            self.status(f"글자 뽑는 중… {int(done)}/{int(total)}쪽")
        self.background(lambda progress: relay.ocr_files(paths, target, out, progress),
                        lambda r: self.done_msg(r), "글자 뽑는 중… (한 쪽에 몇 초씩 걸려요)", on_progress=prog)

    # ── 글로 시키기 ──
    def run_ask(self):
        text = self.ask.text().strip()
        paths = self.files.paths()
        if not text or not paths:
            return
        by_name = {Path(p).name: p for p in paths}
        names = list(by_name)
        model, api = {"ollama": (self.models and self.models[0], None), "builtin": ("local", localai.API)}.get(self.ai_mode, (None, None))
        if self.ai_mode == "ollama":
            model = relay.load_config().get("ollama_model") or model
        online = self.ai_mode == "online"

        def got_plan(r):
            plan, who = r
            plan_paths = [by_name[n] for n in plan["files"]]
            if plan["action"] == "bundle" and SORT[self.sort.currentIndex()][1] == "none" and plan.get("sort", "name") == "name":
                plan["sort"] = "none"                          # 목록에서 정한 순서 존중
                plan_paths = [p for p in paths if p in plan_paths]
            sub = "AI가 이해한 내용" if who != "규칙" else "문장에서 찾은 내용"
            if not self.confirm("이렇게 할까요?", fai.describe(plan), sub=sub):
                return self.status("취소했어요.")
            self.exec_plan(plan, plan_paths)

        self.background(lambda: fai.make_plan(text, names, model, api, online=online), got_plan,
                        "AI가 문장을 읽는 중…" if (model or online) else "문장 읽는 중…")

    def exec_plan(self, plan, paths):
        a = plan["action"]
        if a == "bundle":
            self.run_bundle(None, paths, plan)
        elif a == "imgconv":
            self.run_imgconv(plan["target"], paths)
        elif a == "convert":
            self.run_convert(paths, plan["target"])
        elif a == "ocr":
            self.run_ocr(paths, plan["target"])
        elif a == "split":
            self.run_split(paths, plan.get("format", "jpg"))

    # ── AI 상태 ──
    def set_chip(self, text, state="", tip=""):
        self.ai_chip.setText("● " + text if state == "on" else text)
        self.ai_chip.setToolTip(tip)
        self.ai_chip.setProperty("state", state)
        self.ai_chip.style().unpolish(self.ai_chip); self.ai_chip.style().polish(self.ai_chip)
        self.on_files_changed()

    OFF_TIP = "AI 없이도 모든 버튼은 쓸 수 있어요. AI를 켜면 글로 시키기가 똑똑해져요."

    def check_ai(self):
        self.get_ai_btn.setVisible(False)
        if ONLINE:
            self.set_chip("AI 확인 중…")

            def ok(alive):
                self.ai_mode = "online" if alive else None
                if alive:
                    self.set_chip("AI 켜짐", "on", "글로 시키기와 글자 뽑기에 AI(Claude)를 써요.")
                elif not relay.server_url():
                    self.set_chip("AI 꺼짐", "", self.OFF_TIP + " ⚙ 설정에서 AI를 연결할 수 있어요.")
                else:
                    self.set_chip("AI 연결 안 됨", "warn", "AI에 연결할 수 없어요. 인터넷이나 ⚙ 설정의 주소를 확인해주세요.")
            return self.background(relay.health, ok, "", block=False,
                                   on_fail=lambda m: self.set_chip("AI 연결 안 됨", "warn", m))
        self.models = fai.list_models()
        if self.models:
            self.ai_mode = "ollama"
            return self.set_chip("AI 켜짐", "on", f"이 PC의 Ollama 모델을 써요 ({relay.load_config().get('ollama_model') or self.models[0]})")
        self.ai_mode = None
        if not localai.available():
            return self.set_chip("AI 꺼짐", "", self.OFF_TIP)
        if not localai.has_model():
            self.get_ai_btn.setVisible(True)
            return self.set_chip("AI 꺼짐", "", self.OFF_TIP + " 오른쪽 'AI 켜기'를 누르면 한 번 받아서 인터넷 없이 써요.")
        self.start_builtin()

    def start_builtin(self):
        if self.server.running():
            self.ai_mode = "builtin"
            return self.set_chip("AI 켜짐", "on", "내장 AI · 인터넷 없이 이 PC에서 돌아가요")
        if self.starting:
            return
        self.starting = True
        self.set_chip("AI 켜는 중…")

        def ok(r):
            self.starting = False
            if r:
                self.ai_mode = "builtin"
                self.set_chip("AI 켜짐", "on", "내장 AI · 인터넷 없이 이 PC에서 돌아가요")
            else:
                self.set_chip("AI 꺼짐", "", "내장 AI를 못 켰어요. ⚙ 설정에서 'AI 다시 확인'을 눌러보세요.")
        self.background(self.server.start, ok, "", block=False,
                        on_fail=lambda m: (setattr(self, "starting", False), self.set_chip("AI 꺼짐", "", m)))

    def get_ai(self):
        if not self.confirm("AI를 켤까요?",
                            f"글로 시키기를 더 잘 알아듣는 AI를 받아요.\n\n"
                            f"• 크기: 약 {localai.MODEL_SIZE_MB / 1000:.1f}GB (처음 한 번만)\n"
                            f"• 받은 뒤에는 인터넷 없이 이 PC 안에서만 돌아가요", yes="받기"):
            return
        self.get_ai_btn.setEnabled(False)

        def prog(got, total):
            self.get_ai_btn.setText(f"AI 받는 중 {min(99, int(got / total * 100))}%")

        def ok(_):
            self.get_ai_btn.setVisible(False)
            self.get_ai_btn.setEnabled(True)
            self.start_builtin()

        def bad(m):
            self.get_ai_btn.setText("AI 켜기 (다시 받기)")
            self.get_ai_btn.setEnabled(True)
            self.status("✗ AI를 받지 못했어요: " + m, "err")
        self.background(localai.download_model, ok, "", on_fail=bad, block=False, on_progress=prog)

    def open_settings(self):
        d = QDialog(self); d.setWindowTitle("설정"); d.setMinimumWidth(460)
        v = QVBoxLayout(d); v.setSpacing(10)
        v.addWidget(label("설정", "cardtitle"))
        url = None
        model_box = None
        if ONLINE:
            v.addWidget(label("AI를 연결하면 자유로운 문장도 알아듣고, 사진 속 글자도 뽑을 수 있어요. "
                              "연결하지 않아도 나머지 기능은 모두 쓸 수 있어요.", "desc", wrap=True))
            v.addWidget(label("AI 연결 주소 (선택)"))
            url = QLineEdit(relay.server_url()); url.setPlaceholderText("https://file-converter-relay.….workers.dev")
            v.addWidget(url)
        else:
            v.addWidget(label("이 버전은 인터넷 없이 PC 안에서만 동작해요. AI도 PC 안에서 돌아가요.", "desc", wrap=True))
            if self.models:
                v.addWidget(label("사용할 AI 모델 (Ollama)"))
                model_box = QComboBox(); model_box.addItems(self.models)
                cur = relay.load_config().get("ollama_model")
                if cur in self.models:
                    model_box.setCurrentText(cur)
                v.addWidget(model_box)
        recheck = QPushButton("AI 다시 확인"); recheck.clicked.connect(lambda: (d.accept(), self.check_ai()))
        v.addWidget(recheck)
        bb = QDialogButtonBox(); bb.addButton("저장", QDialogButtonBox.AcceptRole); bb.addButton("취소", QDialogButtonBox.RejectRole)
        bb.accepted.connect(d.accept); bb.rejected.connect(d.reject)
        v.addWidget(bb)
        if d.exec() == QDialog.Accepted:
            if url is not None:
                relay.save_config(relay_url=url.text().strip())
            if model_box is not None:
                relay.save_config(ollama_model=model_box.currentText())
            self.check_ai()

    def closeEvent(self, e):
        self.server.stop()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    f = QFont()
    f.setFamilies(["Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "sans-serif"])
    app.setFont(f)
    import tempfile
    arrow = Path(tempfile.gettempdir()) / "fconv_arrow.svg"
    arrow.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
                     '<path d="M1 3l4 4 4-4" fill="none" stroke="#667085" stroke-width="1.6"/></svg>')
    app.setStyleSheet(STYLE.replace("ARROW", arrow.as_posix()))
    w = Main()
    w.show()
    if len(sys.argv) > 1:                       # 파일을 exe 아이콘에 끌어다 놓아도 열림
        w.files.add_paths(sys.argv[1:])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
