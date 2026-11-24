#!/usr/bin/env python3
"""Beamer Presenter Lite: lightweight beamer presenter (PyQt6 + pypdfium2, offline).

  beamer-presenter-lite main-notes.pdf [-d MINUTES] [-l LAYOUT]
  beamer-presenter-lite --edit main.pdf       # notes editor (Emacs keys) beside the slides
  beamer-presenter-lite --install-desktop     # add to the desktop app menu (Linux)

Speaker notes come from the PDF's right half (beamer "show notes on second screen")
or from a Markdown file (--notes FILE, or <pdf name>.notes.md next to the PDF);
see load_notes() for the format. The Markdown file is reloaded when it changes.

PDF built with \\setbeameroption{show notes on second screen=right}: each page
is slide | notes side by side, split automatically. Plain PDFs work too.
With two screens the audience window goes fullscreen on the second one.
"""
import argparse
from collections import OrderedDict
from datetime import datetime
import os
import re
import shutil
import sys
import time

import pypdfium2 as pdfium
from pypdf import PdfReader

from PyQt6.QtCore import QByteArray, QEvent, QFileSystemWatcher, QPointF, QRectF, QSize, QSizeF, Qt, QTimer, QUrl
from PyQt6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QImage, QPainter, QPainterPath,
                         QPen, QPixmap, QPolygonF, QRadialGradient, QSyntaxHighlighter, QTextBlockFormat,
                         QTextCharFormat, QTextCursor, QTextDocument)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PyQt6.QtWidgets import (QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                             QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
                             QSlider, QSplitter, QStyle, QTextBrowser, QVBoxLayout, QWidget)

MODES = ['laser', 'pointer', 'pen', 'eraser', 'off']
PEN_COLORS = [
    ('Red', '#d93829'),
    ('Blue', '#2563c9'),
    ('Green', '#1f8a4c'),
    ('Amber', '#d48806'),
]
HEAD_RE = re.compile(r'#[ \t]+(B?\d+)(?:\.(\d+)(?:-(\d+))?)?(?=\s|$)(.*)')   # notes heading, see load_notes

PRESENTER_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#242428"/>
      <stop offset="100%" stop-color="#131316"/>
    </linearGradient>
    <linearGradient id="slide" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f7f6f2"/>
      <stop offset="100%" stop-color="#e8e6e0"/>
    </linearGradient>
    <radialGradient id="laserGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#e0483a" stop-opacity="0.55"/>
      <stop offset="55%" stop-color="#e0483a" stop-opacity="0.16"/>
      <stop offset="100%" stop-color="#e0483a" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="laserCore" cx="42%" cy="38%" r="60%">
      <stop offset="0%" stop-color="#ff9a8f"/>
      <stop offset="45%" stop-color="#e4483a"/>
      <stop offset="100%" stop-color="#c42f23"/>
    </radialGradient>
  </defs>
  <rect x="6" y="6" width="116" height="116" rx="24" fill="url(#bg)"/>
  <rect x="6.75" y="6.75" width="114.5" height="114.5" rx="23.25" fill="none" stroke="#383840" stroke-width="1.5"/>
  <rect x="34" y="42" width="74" height="58" rx="6" fill="#2a2a31" stroke="#42424c" stroke-width="1.5"/>
  <rect x="44" y="84" width="32" height="4" rx="2" fill="#52525d"/>
  <rect x="82" y="84" width="16" height="4" rx="2" fill="#41414b"/>
  <rect x="20" y="26" width="78" height="56" rx="6" fill="#09090b" opacity="0.48" transform="translate(0 3)"/>
  <rect x="20" y="26" width="78" height="56" rx="6" fill="url(#slide)"/>
  <path d="M26 26 H92 A6 6 0 0 1 98 32 V39 H20 V32 A6 6 0 0 1 26 26 Z" fill="#32343d"/>
  <path d="M20.75 39 V32 A5.25 5.25 0 0 1 26 26.75 H92 A5.25 5.25 0 0 1 97.25 32 V39" fill="none" stroke="#4b4e5a" stroke-width="1.2"/>
  <rect x="28" y="31" width="30" height="3.5" rx="1.75" fill="#eeede8"/>
  <rect x="28" y="48" width="28" height="4" rx="2" fill="#686870"/>
  <rect x="28" y="57" width="22" height="3.5" rx="1.75" fill="#a2a2aa"/>
  <rect x="28" y="65" width="26" height="3.5" rx="1.75" fill="#a2a2aa"/>
  <rect x="63" y="47" width="27" height="25" rx="3" fill="#dcdad3"/>
  <circle cx="76.5" cy="59.5" r="15" fill="url(#laserGlow)"/>
  <circle cx="76.5" cy="59.5" r="6.2" fill="url(#laserCore)"/>
</svg>
"""

EDITOR_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#242428"/>
      <stop offset="100%" stop-color="#131316"/>
    </linearGradient>
    <linearGradient id="slide" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f7f6f2"/>
      <stop offset="100%" stop-color="#e8e6e0"/>
    </linearGradient>
  </defs>
  <rect x="6" y="6" width="116" height="116" rx="24" fill="url(#bg)"/>
  <rect x="6.75" y="6.75" width="114.5" height="114.5" rx="23.25" fill="none" stroke="#383840" stroke-width="1.5"/>
  <rect x="20" y="24" width="52" height="38" rx="5" fill="url(#slide)"/>
  <path d="M25 24 H67 A5 5 0 0 1 72 29 V34 H20 V29 A5 5 0 0 1 25 24 Z" fill="#32343d"/>
  <path d="M20.75 34 V29 A4.25 4.25 0 0 1 25 24.75 H67 A4.25 4.25 0 0 1 71.25 29 V34" fill="none" stroke="#4b4e5a" stroke-width="1.1"/>
  <rect x="26" y="28" width="20" height="2.8" rx="1.4" fill="#eeede8"/>
  <rect x="26" y="40" width="24" height="3" rx="1.5" fill="#7c7c85"/>
  <rect x="26" y="47" width="32" height="3" rx="1.5" fill="#b0b0b8"/>
  <rect x="44" y="44" width="64" height="60" rx="6" fill="#09090b" opacity="0.48" transform="translate(0 3)"/>
  <rect x="44" y="44" width="64" height="60" rx="6" fill="#25252b" stroke="#4e4e58" stroke-width="1.5"/>
  <rect x="53" y="55" width="7" height="4.5" rx="1.5" fill="#e0483a"/>
  <rect x="64" y="55" width="28" height="4.5" rx="2" fill="#f0efeb"/>
  <rect x="53" y="67" width="44" height="3.5" rx="1.75" fill="#9898a2"/>
  <rect x="53" y="76" width="38" height="3.5" rx="1.75" fill="#9898a2"/>
  <rect x="53" y="85" width="24" height="3.5" rx="1.75" fill="#9898a2"/>
  <rect x="81" y="82.5" width="2.8" height="9" rx="1.2" fill="#e0483a"/>
</svg>
"""


def make_icon(svg_text):
    """Render an embedded SVG string into a crisp multi-resolution QIcon."""
    icon = QIcon()
    try:
        from PyQt6.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(QByteArray(svg_text.encode('utf-8')))
        if renderer.isValid():
            for sz in (16, 24, 32, 48, 64, 128, 256):
                pm = QPixmap(sz, sz)
                pm.fill(Qt.GlobalColor.transparent)
                p = QPainter(pm)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                renderer.render(p, QRectF(0, 0, sz, sz))
                p.end()
                icon.addPixmap(pm)
            return icon
    except Exception:
        pass
    return icon


def make_layout_icon(kind):
    """Crisp 16x12 schematic wireframe icon for presenter layout & swap buttons."""
    pm = QPixmap(32, 24)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor('#b8b8c0'), 1.2)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == 1:
        # Side: slide left | next over notes right
        p.drawRoundedRect(QRectF(1, 1, 14, 10), 1.2, 1.2)
        p.drawLine(QPointF(9, 1), QPointF(9, 11))
        p.drawLine(QPointF(9, 5), QPointF(15, 5))
        p.fillRect(QRectF(10.2, 6.2, 3.6, 3.6), QColor('#7e7e88'))
    elif kind == 2:
        # Stack: current|next top / big notes bottom
        p.drawRoundedRect(QRectF(1, 1, 14, 10), 1.2, 1.2)
        p.drawLine(QPointF(1, 6), QPointF(15, 6))
        p.drawLine(QPointF(8, 1), QPointF(8, 6))
        p.fillRect(QRectF(2.2, 7.2, 11.6, 2.6), QColor('#7e7e88'))
    elif kind == 3:
        # Slides only: current | next
        p.drawRoundedRect(QRectF(1, 1, 14, 10), 1.2, 1.2)
        p.drawLine(QPointF(8, 1), QPointF(8, 11))
    else:
        # Swap arrows
        p.drawLine(QPointF(2.5, 4), QPointF(13.5, 4))
        p.drawLine(QPointF(10.8, 1.8), QPointF(13.5, 4))
        p.drawLine(QPointF(10.8, 6.2), QPointF(13.5, 4))
        p.drawLine(QPointF(13.5, 8.5), QPointF(2.5, 8.5))
        p.drawLine(QPointF(5.2, 6.3), QPointF(2.5, 8.5))
        p.drawLine(QPointF(5.2, 10.7), QPointF(2.5, 8.5))
    p.end()
    return QIcon(pm)


APP_QSS = """
QWidget {
    background: #0e0e10;
    color: #ecebea;
    font-family: "Inter", "Noto Sans", "Segoe UI", system-ui, sans-serif;
}
QWidget#paneGrid {
    background: #242428;
}
QFrame#pane {
    background: #141416;
    border: none;
}
QFrame#paneHeader {
    background: #121214;
    border: none;
    border-bottom: 1px solid #242428;
}
QLabel#paneTitle {
    background: transparent;
    color: #c8c8ce;
    font-size: 12px;
    font-weight: 500;
}
QLabel#paneMeta {
    background: transparent;
    color: #6e6e75;
    font-size: 12px;
    font-weight: 400;
}
QFrame#statusBar {
    background: #121214;
    border: none;
}
QFrame#vbar {
    background: #131315;
    border: none;
    border-top: 1px solid #242428;
}
QFrame#footerBar {
    background: #101012;
    border: none;
    border-top: 1px solid #242428;
}
QFrame#vSep {
    background: #242428;
    min-width: 1px;
    max-width: 1px;
}
QLabel#statLabel {
    background: transparent;
    color: #6e6e75;
    font-size: 10px;
    font-weight: 500;
}
QLabel#statHero {
    background: transparent;
    color: #ecebea;
    font-family: "JetBrains Mono", "IBM Plex Mono", "DejaVu Sans Mono", monospace;
    font-size: 26px;
    font-weight: 600;
}
QLabel#statValue {
    background: transparent;
    color: #d4d4d8;
    font-family: "JetBrains Mono", "IBM Plex Mono", "DejaVu Sans Mono", monospace;
    font-size: 15px;
    font-weight: 500;
}
QLabel#statMuted {
    background: transparent;
    color: #84848c;
    font-family: "JetBrains Mono", "IBM Plex Mono", "DejaVu Sans Mono", monospace;
    font-size: 15px;
    font-weight: 400;
}
QLabel#modePill {
    background: #1a1a1e;
    color: #c8c8ce;
    border: 1px solid #2a2a30;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 500;
}
QLabel#blankBadgeBlack {
    background: #2a1514;
    color: #ef6a5d;
    border: 1px solid #6b2924;
    border-radius: 4px;
    padding: 4px 9px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#blankBadgeWhite {
    background: #28282d;
    color: #f4f3ef;
    border: 1px solid #52525b;
    border-radius: 4px;
    padding: 4px 9px;
    font-size: 11px;
    font-weight: 600;
}
QLabel#jumpBadge {
    background: #211817;
    color: #f4f3ef;
    border: 1px solid #d9483b;
    border-radius: 4px;
    padding: 4px 9px;
    font-family: "JetBrains Mono", "IBM Plex Mono", "DejaVu Sans Mono", monospace;
    font-size: 12px;
    font-weight: 600;
}
QPushButton {
    background: #1c1c20;
    color: #d4d4d8;
    border: 1px solid #2c2c32;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 500;
}
QPushButton:hover {
    background: #25252a;
    border-color: #3d3d45;
    color: #f4f3ef;
}
QPushButton:pressed {
    background: #17171a;
}
QPushButton#toolBtn {
    background: transparent;
    color: #96969e;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
}
QPushButton#toolBtn:hover {
    background: #1f1f24;
    color: #ecebea;
    border-color: #2c2c32;
}
QPushButton#toolBtnActive {
    background: #242429;
    color: #f4f3ef;
    border: 1px solid #d9483b;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 500;
}
QPushButton#swatchBtn {
    background: transparent;
    border: 1px solid #2c2c32;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    color: #96969e;
}
QPushButton#swatchBtn:hover {
    background: #1f1f24;
    border-color: #3e3e46;
}
QPushButton#saveBtn {
    background: transparent;
    color: #84848c;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 500;
}
QPushButton#saveBtn:hover {
    background: #1f1f24;
    color: #ecebea;
    border-color: #2c2c32;
}
QPushButton#saveBtnDirty {
    background: #2b1817;
    color: #f5c6c2;
    border: 1px solid #8a352d;
    border-radius: 4px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 500;
}
QPushButton#saveBtnDirty:hover {
    background: #381e1c;
    border-color: #d9483b;
    color: #ffffff;
}
QLineEdit {
    background: #161619;
    color: #ecebea;
    border: 1px solid #2b2b31;
    border-radius: 4px;
    padding: 5px 9px;
    selection-background-color: #4a2a28;
}
QLineEdit:focus {
    border-color: #6e6e78;
}
QLineEdit#minibuffer {
    background: #111113;
    color: #8d8d95;
    border: none;
    border-top: 1px solid #242428;
    border-radius: 0px;
    padding: 6px 12px;
    font-family: "JetBrains Mono", "IBM Plex Mono", "DejaVu Sans Mono", monospace;
    font-size: 12px;
}
QLineEdit#minibuffer:focus {
    color: #ecebea;
    border-top: 1px solid #52525b;
}
QPlainTextEdit {
    background: #141416;
    color: #e2e1de;
    border: none;
    selection-background-color: #3a3a44;
}
QTextBrowser {
    background: #141416;
    color: #e2e1de;
    border: none;
    selection-background-color: #3a3a44;
}
QSlider::groove:horizontal {
    height: 3px;
    background: #29292f;
    border-radius: 1px;
}
QSlider::sub-page:horizontal {
    background: #d9483b;
    border-radius: 1px;
}
QSlider::handle:horizontal {
    background: #ecebea;
    width: 10px;
    height: 10px;
    margin: -4px 0;
    border-radius: 5px;
}
QSplitter::handle {
    background: #242428;
    width: 1px;
    height: 1px;
}
QSplitter::handle:hover {
    background: #52525b;
}
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 2px 1px;
}
QScrollBar::handle:vertical {
    background: #2e2e34;
    min-height: 24px;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover {
    background: #4c4c55;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QFrame#helpBox {
    background: #141416;
    border: 1px solid #2e2e34;
    border-radius: 6px;
}
QPushButton#thumbTile {
    background: #151517;
    border: 1px solid #26262b;
    border-radius: 4px;
    padding: 0px;
}
QPushButton#thumbTile:hover {
    background: #1c1c20;
    border-color: #46464f;
}
QPushButton#thumbTileCurrent {
    background: #1a1819;
    border: 2px solid #d9483b;
    border-radius: 4px;
    padding: 0px;
}
"""


def notes_css(font_px=20):
    return f"""
    body {{
        color: #dfdeda;
        font-size: {font_px}px;
        line-height: 1.55;
    }}
    a {{ color: #d98276; }}
    """


def style_notes_document(doc, font_px=20):
    """Apply clean darkroom typography directly to Qt's Markdown QTextDocument blocks."""
    doc.setDocumentMargin(16)
    base_font = QFont()
    base_font.setPixelSize(font_px)
    doc.setDefaultFont(base_font)

    mono_family = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
    c = QTextCursor(doc)
    b = doc.firstBlock()
    while b.isValid():
        bf = b.blockFormat()
        heading = bf.headingLevel()
        new_bf = QTextBlockFormat(bf)
        new_bf.setLineHeight(148, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        if heading > 0:
            new_bf.setTopMargin(4 if b == doc.firstBlock() else 14)
            new_bf.setBottomMargin(8)
            c.setPosition(b.position())
            c.setBlockFormat(new_bf)
            c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cf = QTextCharFormat()
            cf.setForeground(QColor('#f4f3ef'))
            hf = QFont(base_font)
            hf.setWeight(QFont.Weight.DemiBold)
            scale = 1.22 if heading <= 2 else 1.12
            hf.setPixelSize(max(15, int(font_px * scale)))
            cf.setFont(hf)
            c.mergeCharFormat(cf)
        else:
            is_code_blk = bool(b.charFormat().fontFixedPitch()) or bool(bf.nonBreakableLines())
            is_quote = bf.leftMargin() > 0 and b.textList() is None and not is_code_blk
            if is_code_blk:
                new_bf.setTopMargin(4)
                new_bf.setBottomMargin(4)
                new_bf.setLeftMargin(10)
                new_bf.setRightMargin(10)
                new_bf.setBackground(QColor('#1a1a1e'))
            elif b.textList() is not None:
                new_bf.setTopMargin(3)
                new_bf.setBottomMargin(4)
            elif is_quote:
                new_bf.setTopMargin(8)
                new_bf.setBottomMargin(8)
                new_bf.setLeftMargin(14)
            else:
                new_bf.setTopMargin(4)
                new_bf.setBottomMargin(8)
            c.setPosition(b.position())
            c.setBlockFormat(new_bf)
            if is_code_blk:
                c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cf = QTextCharFormat()
                mf = QFont(mono_family)
                mf.setPixelSize(max(12, int(font_px * 0.84)))
                cf.setFont(mf)
                cf.setForeground(QColor('#d4d4dc'))
                c.mergeCharFormat(cf)
            elif is_quote:
                c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                cf = QTextCharFormat()
                cf.setForeground(QColor('#9c9ca4'))
                cf.setFontItalic(True)
                c.mergeCharFormat(cf)
            # Style inline code spans cleanly
            if not is_code_blk:
                it = b.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid() and frag.charFormat().fontFixedPitch():
                        c.setPosition(frag.position())
                        c.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
                        cf = QTextCharFormat()
                        mf = QFont(mono_family)
                        mf.setPixelSize(max(12, int(font_px * 0.86)))
                        cf.setFont(mf)
                        cf.setForeground(QColor('#d8a657'))
                        cf.setBackground(QColor('#1e1e22'))
                        c.mergeCharFormat(cf)
                    it += 1
        b = b.next()


def fmt(s):
    neg, t = s < 0, int(abs(s))
    h, m, sec = t // 3600, t // 60 % 60, t % 60
    return ('-' if neg else '') + (f'{h}:{m:02}:{sec:02}' if h else f'{m}:{sec:02}')


def parse_time(text):
    """'12' -> 12 min, '12:30' -> 12m30s, '1:02:00' -> 1h2m. Leading '-' allowed. Returns seconds."""
    text = text.strip()
    sign = -1 if text.startswith('-') else 1
    parts = [float(x) for x in text.lstrip('-').split(':')]
    if len(parts) == 1:
        return sign * parts[0] * 60
    if len(parts) > 3:
        raise ValueError(text)
    secs = 0.0
    for x in parts:
        secs = secs * 60 + x
    return sign * secs


class Pdf:
    """pypdfium2 wrapper with an LRU image cache for fast slide transitions."""

    def __init__(self, path, cache_size=48):
        self.doc = pdfium.PdfDocument(path)
        self._cache = OrderedDict()
        self._cache_size = cache_size
        self._sizes = {}

    def pageCount(self):
        return len(self.doc)

    def pagePointSize(self, i):
        if i not in self._sizes:
            self._sizes[i] = QSizeF(*self.doc[i].get_size())
        return self._sizes[i]

    def render(self, i, size):
        page = self.doc[i]
        h = max(1, size.height())
        bm = page.render(scale=h / page.get_size()[1], rev_byteorder=True, prefer_bgrx=True)
        return QImage(bytes(bm.buffer), bm.width, bm.height, bm.stride, QImage.Format.Format_RGBX8888).copy()

    def render_half(self, i, half, split, width, height, dpr=1.0):
        w, h = max(1, round(width * dpr)), max(1, round(height * dpr))
        key = (i, half, split, w, h, round(dpr, 2))
        img = self._cache.get(key)
        if img is not None:
            self._cache.move_to_end(key)
            return img
        full = self.render(i, QSize(w * (2 if split else 1), h))
        img = full.copy(half * w, 0, w, h) if split else full
        img.setDevicePixelRatio(dpr)
        self._cache[key] = img
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return img


def find_movies(path, split):
    """{page: [(QRectF in 0..1 slide coords, abs video path)]} for \\movie annotations."""
    base, out = os.path.dirname(os.path.abspath(path)), {}
    for i, page in enumerate(PdfReader(path).pages):
        mb = page.mediabox
        W, H = float(mb.width), float(mb.height)
        pw = W / 2 if split else W
        for a in page.get('/Annots') or []:
            a = a.get_object()
            if a.get('/Subtype') != '/Movie':
                continue
            f = a['/Movie']['/F']
            if hasattr(f, 'get'):                      # file specification dictionary
                f = f.get('/UF') or f.get('/F')
            x1, y1, x2, y2 = (float(v) for v in a['/Rect'])
            x1, x2, y1, y2 = min(x1, x2) - float(mb.left), max(x1, x2) - float(mb.left), \
                min(y1, y2) - float(mb.bottom), max(y1, y2) - float(mb.bottom)
            rect = QRectF(x1 / pw, (H - y2) / H, (x2 - x1) / pw, (y2 - y1) / H)   # PDF origin is bottom-left
            out.setdefault(i, []).append((rect, os.path.join(base, str(f))))
    return out


def page_keys(path):
    """(frame, overlay) for each page, from beamer's page labels (= frame number).
    Frames after the numbering restarts (appendixnumberbeamer) become B1, B2, ..."""
    keys, prev, backup, ov = [], None, False, 0
    for label in PdfReader(path).page_labels:
        if label == prev:
            ov += 1     # ponytail: a \noframenumbering frame looks like an overlay of the previous one
        else:
            ov = 1
            if prev and label.isdigit() and prev.isdigit() and int(label) < int(prev):
                backup = True
        prev = label
        keys.append((('B' if backup else '') + label, ov))
    return keys


def load_notes(path):
    """Markdown speaker notes. A line '# KEY [heading]' starts the notes for a frame:
         # 4            every page (overlay) of frame 4
         # 4.2          only overlay 2 of frame 4
         # 5.1-3        overlays 1 to 3 of frame 5
         # B1           backup frame 1 (numbering restarted after \\appendix)
    Frame numbers are the ones in the slide footer. A page shows every matching section,
    in file order. Anything else (## headings, lists, code, ...) is the note body.
    Returns [(frame, first overlay or None, last overlay, markdown)]."""
    with open(path, encoding='utf-8') as f:
        return parse_notes(f.read())


def parse_notes(text):
    secs, cur, fence = [], None, False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith(('```', '~~~')):
            fence = not fence
        m = not fence and HEAD_RE.match(line)
        if m:
            frame, lo, hi, title = m.groups()
            lo = int(lo) if lo else None
            cur = [frame, lo, int(hi) if hi else lo, f'### {title.strip()}\n' if title.strip() else '']
            secs.append(cur)
        elif cur:
            cur[3] += line
    return secs


def notes_for(secs, key):
    """Markdown shown for a page whose (frame, overlay) is key."""
    frame, ov = key
    return '\n\n'.join(md for f, lo, hi, md in secs if f == frame and (lo is None or lo <= ov <= hi))


def iter_heading_blocks(doc):
    """Yield (QTextBlock, match) for every notes heading outside fenced code blocks."""
    fence = False
    b = doc.firstBlock()
    while b.isValid():
        txt = b.text()
        if txt.lstrip().startswith(('```', '~~~')):
            fence = not fence
        elif not fence:
            m = HEAD_RE.match(txt)
            if m:
                yield b, m
        b = b.next()


def install_desktop(remove=False):
    """Write (or remove) .desktop entries and dedicated SVG icons for the Linux app menu."""
    data = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    exe = shutil.which('beamer-presenter-lite') or os.path.abspath(sys.argv[0])
    icon_dir = os.path.join(data, 'icons', 'hicolor', 'scalable', 'apps')
    for name, title, comment, arg, svg in [
            ('beamer-presenter-lite', 'Beamer Presenter Lite',
             'Present beamer PDFs with speaker notes, pointer, timer and video', '', PRESENTER_ICON_SVG),
            ('beamer-notes-editor', 'Beamer Notes Editor',
             'Edit Markdown speaker notes beside the slides (Emacs keys)', ' --edit', EDITOR_ICON_SVG)]:
        path = os.path.join(data, 'applications', name + '.desktop')
        icon_path = os.path.join(icon_dir, name + '.svg')
        if remove:
            for p in (path, icon_path):
                if os.path.exists(p):
                    os.remove(p)
                    print('removed ' + p)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            os.makedirs(icon_dir, exist_ok=True)
            with open(icon_path, 'w', encoding='utf-8') as f:
                f.write(svg)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(f'[Desktop Entry]\nType=Application\nName={title}\nComment={comment}\n'
                        f'Exec={exe}{arg} %f\nIcon={name}\nTerminal=false\n'
                        'Categories=Office;Viewer;\nMimeType=application/pdf;\n')
            print('wrote ' + icon_path)
            print('wrote ' + path)


def make_pane(title, widget, extra_widgets=()):
    """Architectural flat pane with a slim hairline header bar."""
    pane = QFrame()
    pane.setObjectName('pane')
    lay = QVBoxLayout(pane)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    hdr = QFrame()
    hdr.setObjectName('paneHeader')
    hdr.setFixedHeight(32)
    hl = QHBoxLayout(hdr)
    hl.setContentsMargins(12, 0, 8, 0)
    hl.setSpacing(8)
    lbl = QLabel(title)
    lbl.setObjectName('paneTitle')
    meta = QLabel('')
    meta.setObjectName('paneMeta')
    hl.addWidget(lbl)
    hl.addWidget(meta)
    hl.addStretch(1)
    for w in extra_widgets:
        hl.addWidget(w)

    lay.addWidget(hdr)
    lay.addWidget(widget, 1)
    pane._title_label = lbl
    pane._meta_label = meta
    return pane


class ProgressBar(QWidget):
    """Razor-slim dual-track pace hairline: slide progress (top) vs elapsed time pace (bottom)."""

    def __init__(self):
        super().__init__()
        self.slide_frac = 0.0
        self.time_frac = 0.0
        self.overtime = False
        self.setFixedHeight(5)

    def set_progress(self, slide_frac, time_frac):
        self.slide_frac = max(0.0, min(1.0, slide_frac))
        self.overtime = time_frac > 1.0
        self.time_frac = max(0.0, min(1.0, time_frac))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        w, h = self.width(), self.height()
        if w <= 1:
            p.end()
            return
        p.fillRect(0, 0, w, h, QColor('#1a1a1e'))
        sw = round(w * self.slide_frac)
        if sw > 0:
            p.fillRect(0, 0, sw, 2, QColor('#9a9aa2'))
        tw = round(w * self.time_frac)
        if tw > 0:
            if self.overtime:
                tc = QColor('#d9483b')
            elif self.time_frac > self.slide_frac + 0.12:
                tc = QColor('#d4912a')
            else:
                tc = QColor('#4ea06b')
            p.fillRect(0, 3, tw, 2, tc)
        p.end()


class SlideView(QWidget):
    """Draws one half (0 = slide, 1 = notes) of a PDF page, fitted and centered."""

    def __init__(self, doc, split, half=0, bg='#0b0b0c'):
        super().__init__()
        self.doc, self.split, self.half, self.page = doc, split, half, 0
        self.pointer, self.mode = None, 'laser'   # pointer: (rx, ry) in 0..1 or None
        self.pen_color = PEN_COLORS[0][1]
        self.blank = None                          # None | 'black' | 'white'
        self.frame = None                          # (QRectF 0..1, QImage) video frame overlay
        self.full = False                          # video frame fills the whole widget
        self.annotations = None                    # shared dict {page: [(color, [(rx, ry), ...])]}
        self.setStyleSheet(f'background:{bg}')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

    def target(self):
        """Rect where the slide image is drawn, or None if nothing to draw."""
        if self.width() <= 0 or self.height() <= 0:
            return None
        if not (0 <= self.page < self.doc.pageCount()) or (self.half and not self.split):
            return None
        ps = self.doc.pagePointSize(self.page)
        pw, ph = ps.width() / (2 if self.split else 1), ps.height()
        if pw <= 0 or ph <= 0:
            return None
        s = min(self.width() / pw, self.height() / ph)
        w, h = pw * s, ph * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def image(self, r):
        return self.doc.render_half(self.page, self.half, self.split, r.width(), r.height(), self.devicePixelRatioF())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.blank == 'black':
            p.fillRect(self.rect(), Qt.GlobalColor.black)
            p.end()
            return
        if self.blank == 'white':
            p.fillRect(self.rect(), Qt.GlobalColor.white)
            p.end()
            return
        r = self.target()
        if r is None:
            p.end()
            return
        has_frame = self.frame is not None and not self.frame[1].isNull()
        if not (has_frame and self.full):
            p.fillRect(r, Qt.GlobalColor.white)   # PDF pages may render transparent
            p.drawImage(r.topLeft(), self.image(r))
        if has_frame:
            fr, img = self.frame
            box = QRectF(self.rect()) if self.full else \
                QRectF(r.x() + fr.x() * r.width(), r.y() + fr.y() * r.height(),
                       fr.width() * r.width(), fr.height() * r.height())
            sz = img.size().toSizeF().scaled(box.size(), Qt.AspectRatioMode.KeepAspectRatio)
            p.fillRect(box, Qt.GlobalColor.black)
            p.drawImage(QRectF(box.center().x() - sz.width() / 2, box.center().y() - sz.height() / 2,
                               sz.width(), sz.height()), img)
        # Hand-drawn annotations for the current slide
        if self.annotations and not (has_frame and self.full):
            strokes = self.annotations.get(self.page)
            if strokes:
                pen_w = max(2.0, r.width() / 240.0)
                for color_hex, pts in strokes:
                    if not pts:
                        continue
                    pen = QPen(QColor(color_hex), pen_w, Qt.PenStyle.SolidLine,
                               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                    p.setPen(pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    if len(pts) == 1:
                        x, y = r.x() + pts[0][0] * r.width(), r.y() + pts[0][1] * r.height()
                        p.drawPoint(QPointF(x, y))
                    else:
                        path = QPainterPath()
                        path.moveTo(r.x() + pts[0][0] * r.width(), r.y() + pts[0][1] * r.height())
                        for rx, ry in pts[1:]:
                            path.lineTo(r.x() + rx * r.width(), r.y() + ry * r.height())
                        p.drawPath(path)
        if self.pointer and self.mode != 'off':
            x, y = r.x() + self.pointer[0] * r.width(), r.y() + self.pointer[1] * r.height()
            if self.mode == 'laser':
                rad = max(8.0, r.width() / 120)
                g = QRadialGradient(QPointF(x, y), rad * 2)
                g.setColorAt(0, QColor(255, 40, 40, 255))
                g.setColorAt(0.35, QColor(255, 0, 0, 200))
                g.setColorAt(1, QColor(255, 0, 0, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(g)
                p.drawEllipse(QPointF(x, y), rad * 2, rad * 2)
            elif self.mode == 'pen':
                rad = max(4.0, r.width() / 260)
                p.setPen(QPen(QColor('#ffffff'), 1.5))
                p.setBrush(QBrush(QColor(self.pen_color)))
                p.drawEllipse(QPointF(x, y), rad, rad)
            elif self.mode == 'eraser':
                rad = max(10.0, r.width() * 0.025)
                p.setPen(QPen(QColor('#e8ecf2'), 1.5, Qt.PenStyle.DashLine))
                p.setBrush(QBrush(QColor(255, 255, 255, 45)))
                p.drawEllipse(QPointF(x, y), rad, rad)
            else:
                k = max(1.0, r.width() / 900)
                pts = [(0, 0), (0, 26), (7, 20), (12, 31), (16, 29), (11, 18), (20, 18)]
                p.setPen(QColor('black'))
                p.setBrush(QColor('#ffd400'))
                p.drawPolygon(QPolygonF([QPointF(x + a * k, y + b * k) for a, b in pts]))
        p.end()


class Audience(SlideView):
    def __init__(self, app):
        super().__init__(app.doc, app.split, bg='black')
        self.app = app
        self.setWindowTitle('Audience')
        self.setCursor(Qt.CursorShape.BlankCursor)

    def keyPressEvent(self, e):
        self.app.key(e, self)


class HelpOverlay(QFrame):
    """Darkroom keyboard shortcut reference overlaid on the Presenter window."""

    SECTIONS = [
        ('Navigation', [
            ('→ / Space / Enter / J', 'Next slide'),
            ('← / Shift+Enter / BS / K', 'Previous slide'),
            ('num + Enter', 'Jump to slide / frame number'),
            ('Home / End', 'First / Last slide'),
            ('G', 'Slide overview'),
            (': / Ctrl+G', 'Jump dialog (frame or pN)'),
        ]),
        ('Pointer & Pen', [
            ('L', 'Cycle mode (laser / pointer / pen / eraser / off)'),
            ('D / E', 'Toggle pen / eraser'),
            ('Right-drag (pen)', 'Quick erase'),
            ('P', 'Cycle pen color'),
            ('U / Ctrl+Z', 'Undo last stroke'),
            ('C / Shift+C', 'Clear page / all drawings'),
        ]),
        ('Timer & Notes', [
            ('S / R', 'Start-pause / reset timer'),
            ('T', 'Set remaining time'),
            ('+ / -', 'Adjust remaining ±1 min'),
            ('Ctrl++ / Ctrl+-', 'Notes font size'),
        ]),
        ('Display & Video', [
            ('B / .', 'Blackout audience'),
            ('W / ,', 'Whiteout audience'),
            ('X', 'Swap screens'),
            ('Alt+1 / 2 / 3 (or footer)', 'Switch / swap slide & notes layout'),
            ('V / [ ] / Z', 'Video play, ±5s, fullscreen'),
            ('F / ? / Q', 'Fullscreen, help, quit'),
        ]),
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet('QFrame#helpBackdrop { background: rgba(10, 10, 11, 232); }')
        self.setObjectName('helpBackdrop')
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        box = QFrame()
        box.setObjectName('helpBox')
        box.setMaximumWidth(860)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(28, 22, 28, 24)
        bl.setSpacing(18)

        top = QHBoxLayout()
        title = QLabel('Keyboard Shortcuts')
        title.setStyleSheet('font-size: 16px; font-weight: 600; color: #f4f3ef; background: transparent;')
        close_btn = QPushButton('Close  Esc')
        close_btn.setObjectName('toolBtn')
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.clicked.connect(self.hide)
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(close_btn)
        bl.addLayout(top)

        grid = QGridLayout()
        grid.setHorizontalSpacing(36)
        grid.setVerticalSpacing(18)
        for idx, (sec_name, items) in enumerate(self.SECTIONS):
            rows = ''.join(
                f'<tr><td style="padding:4px 16px 4px 0;color:#ecebea;font-family:monospace;'
                f'font-size:12px;white-space:nowrap">{k}</td>'
                f'<td style="padding:4px 0;color:#9898a0;font-size:12px">{desc}</td></tr>'
                for k, desc in items
            )
            lbl = QLabel(
                f'<div style="color:#c8c8ce;font-size:12px;font-weight:600;'
                f'border-bottom:1px solid #26262b;padding-bottom:5px;margin-bottom:8px">{sec_name}</div>'
                f'<table>{rows}</table>'
            )
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            lbl.setStyleSheet('background: transparent;')
            grid.addWidget(lbl, idx // 2, idx % 2)
        bl.addLayout(grid)
        outer.addWidget(box)
        self.hide()


class OverviewOverlay(QFrame):
    """Responsive thumbnail grid overlay for rapid jump to any slide or backup frame."""

    THUMB_W = 220

    def __init__(self, presenter):
        super().__init__(presenter)
        self.presenter = presenter
        self.cards = []
        self.built = False
        self._cols = 0
        self.setObjectName('overviewBackdrop')
        self.setStyleSheet('QFrame#overviewBackdrop { background: #0e0e10; }')

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 20)
        lay.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(10)
        title = QLabel('Slide Overview')
        title.setStyleSheet('font-size: 15px; font-weight: 600; color: #f4f3ef; background: transparent;')
        self.count_lbl = QLabel('')
        self.count_lbl.setStyleSheet('font-size: 12px; color: #6e6e75; background: transparent;')
        self.jump_input = QLineEdit()
        self.jump_input.setPlaceholderText('Jump to frame (4, B1) or p12…')
        self.jump_input.setFixedWidth(260)
        self.jump_input.returnPressed.connect(self.on_jump_enter)
        close_btn = QPushButton('Close  Esc')
        close_btn.setObjectName('toolBtn')
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.clicked.connect(self.close_overlay)
        top.addWidget(title)
        top.addWidget(self.count_lbl)
        top.addStretch(1)
        top.addWidget(self.jump_input)
        top.addWidget(close_btn)
        lay.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')
        self.container = QWidget()
        self.container.setStyleSheet('background: transparent;')
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.container)
        lay.addWidget(self.scroll, 1)
        self.hide()

    def build(self):
        if self.built:
            return
        self.built = True
        doc = self.presenter.doc
        split = self.presenter.split
        keys = self.presenter.keys
        thumb_w = self.THUMB_W
        ps = doc.pagePointSize(0)
        pw = ps.width() / (2 if split else 1)
        thumb_h = max(80, round(thumb_w * (ps.height() / max(1.0, pw))))
        self.count_lbl.setText(f'{doc.pageCount()} slides')

        for i in range(doc.pageCount()):
            btn = QPushButton()
            btn.setObjectName('thumbTile')
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setFixedSize(thumb_w + 16, thumb_h + 34)
            btn.clicked.connect(lambda _, idx=i: self.pick(idx))

            v = QVBoxLayout(btn)
            v.setContentsMargins(7, 7, 7, 5)
            v.setSpacing(5)
            img_lbl = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
            img_lbl.setFixedSize(thumb_w, thumb_h)
            img = doc.render_half(i, 0, split, thumb_w, thumb_h, 1.0)
            pix = QPixmap.fromImage(img).scaled(thumb_w, thumb_h, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)
            img_lbl.setPixmap(pix)
            img_lbl.setStyleSheet('background: #0b0b0c; border: none;')

            frame, ov = keys[i] if i < len(keys) else (str(i + 1), 1)
            cap_row = QHBoxLayout()
            cap_row.setContentsMargins(1, 0, 1, 0)
            p_lbl = QLabel(f'{i + 1}')
            p_lbl.setStyleSheet('background: transparent; color: #6e6e75; font-size: 11px; font-family: monospace;')
            f_lbl = QLabel(f'Frame {frame}' + (f'.{ov}' if ov > 1 else ''))
            f_lbl.setStyleSheet('background: transparent; color: #c4c4ca; font-size: 11px; font-weight: 500;')
            cap_row.addWidget(p_lbl)
            cap_row.addStretch(1)
            cap_row.addWidget(f_lbl)
            v.addWidget(img_lbl)
            v.addLayout(cap_row)
            self.cards.append(btn)

    def reflow(self):
        if not self.cards:
            return
        avail = max(260, self.width() - 64)
        cols = max(2, avail // (self.THUMB_W + 28))
        if cols == self._cols:
            return
        self._cols = cols
        for i, btn in enumerate(self.cards):
            self.grid.addWidget(btn, i // cols, i % cols)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.built:
            self.reflow()

    def open_overlay(self):
        self.build()
        cur = self.presenter.n
        for i, btn in enumerate(self.cards):
            name = 'thumbTileCurrent' if i == cur else 'thumbTile'
            if btn.objectName() != name:
                btn.setObjectName(name)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        self.jump_input.clear()
        self.jump_input.setStyleSheet('')
        self.setGeometry(self.presenter.rect())
        self.reflow()
        self.show()
        self.raise_()
        if 0 <= cur < len(self.cards):
            self.scroll.ensureWidgetVisible(self.cards[cur], 40, 40)
        self.jump_input.setFocus()

    def close_overlay(self):
        self.hide()
        self.presenter.setFocus()

    def pick(self, idx):
        self.close_overlay()
        self.presenter.go(idx)

    def on_jump_enter(self):
        q = self.jump_input.text().strip()
        if not q:
            return self.close_overlay()
        idx = self.presenter.resolve_jump(q)
        if idx is not None:
            self.pick(idx)
        else:
            self.jump_input.setStyleSheet('border-color: #d9483b;')

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_G):
            self.close_overlay()
        else:
            super().keyPressEvent(e)


class Presenter(QWidget):
    def __init__(self, path, minutes, layout=1, notes=None):
        super().__init__()
        try:
            self.doc = Pdf(path)
            assert self.doc.pageCount() > 0
        except Exception as e:
            QMessageBox.critical(None, 'Beamer Presenter Lite', f'Cannot open {path}\n{e}')
            sys.exit(1)
        ps = self.doc.pagePointSize(0)
        self.split = ps.width() / ps.height() > 2.5
        self.keys = page_keys(path)
        self.n, self.mode, self.dur = -1, 'laser', minutes * 60   # n = -1 until the first go()
        self.since, self.acc = None, 0.0           # timer: running start or None; banked seconds
        self.pen_idx = 0
        self.annotations = {}                      # {page: [(color_hex, [(rx, ry), ...])]}
        self.undo_stack = []                       # [('add', page, stroke) | ('erase', page, idx, stroke) | ('clear', snapshot)]
        self.drawing_stroke = None
        self.erasing = False
        self.note_font_px = 20
        self.jump_buf = ''
        self.layout_swapped = False

        self.setWindowTitle(f'Presenter — {os.path.basename(path)}')
        self.cur = SlideView(self.doc, self.split)
        self.cur.annotations = self.annotations
        self.cur.setMouseTracking(True)
        self.cur.setCursor(Qt.CursorShape.CrossCursor)
        self.cur.mouseMoveEvent = self.on_move
        self.cur.leaveEvent = lambda _: self.set_pointer(None)
        self.cur.mousePressEvent = self.on_press
        self.cur.mouseReleaseEvent = self.on_release
        self.cur.wheelEvent = self.on_wheel

        self.next = SlideView(self.doc, self.split)
        self.next.wheelEvent = self.on_wheel

        auto = os.path.splitext(path)[0] + '.notes.md'
        self.notes_path = notes or (auto if os.path.exists(auto) else None)
        note_btns = []
        if self.notes_path:
            self.notes = QTextBrowser(openExternalLinks=True)
            self.notes.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # keep keys for slide control
            self.notes.document().setDefaultStyleSheet(notes_css(self.note_font_px))
            self.watcher = QFileSystemWatcher([self.notes_path], self)
            self.watcher.fileChanged.connect(self.reload_notes)
            self.reload_notes()
            for txt, delta, tip in (('−', -2, 'Decrease notes size (Ctrl+-)'), ('+', 2, 'Increase notes size (Ctrl++)')):
                b = QPushButton(txt)
                b.setObjectName('toolBtn')
                b.setToolTip(tip)
                b.setFixedWidth(26)
                b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                b.clicked.connect(lambda _, d=delta: self.adjust_note_font(d))
                note_btns.append(b)
        else:
            self.notes = SlideView(self.doc, self.split, half=1)

        self.btn_pen = QPushButton('Pen')
        self.btn_pen.setToolTip('Toggle pen (D)')
        self.btn_color = QPushButton('●')
        self.btn_color.setObjectName('swatchBtn')
        self.btn_color.setToolTip('Cycle pen color (P)')
        self.btn_color.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_color.clicked.connect(self.cycle_pen_color)
        self.btn_eraser = QPushButton('Eraser')
        self.btn_eraser.setToolTip('Toggle eraser (E)')
        self.btn_undo = QPushButton('Undo')
        self.btn_undo.setToolTip('Undo stroke (U / Ctrl+Z)')
        self.btn_clear = QPushButton('Clear')
        self.btn_clear.setToolTip('Clear page drawings (C / Shift+C all)')
        for b, cb in ((self.btn_pen, self.toggle_pen), (self.btn_eraser, self.toggle_eraser),
                      (self.btn_undo, self.undo_stroke), (self.btn_clear, lambda: self.clear_strokes(False))):
            b.setObjectName('toolBtn')
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(cb)
        self.cur_card = make_pane('Current', self.cur,
                                  [self.btn_pen, self.btn_color, self.btn_eraser, self.btn_undo, self.btn_clear])
        self.next_card = make_pane('Next', self.next)
        self.notes_card = make_pane('Notes', self.notes, note_btns)

        # Structured telemetry & timer strip
        def make_stat(label_text, val_obj='statValue'):
            box = QWidget()
            box.setStyleSheet('background: transparent;')
            v = QVBoxLayout(box)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(1)
            lbl = QLabel(label_text)
            lbl.setObjectName('statLabel')
            val = QLabel('—')
            val.setObjectName(val_obj)
            v.addWidget(lbl)
            v.addWidget(val)
            return box, lbl, val

        def make_vsep():
            sep = QFrame()
            sep.setObjectName('vSep')
            sep.setFixedHeight(32)
            return sep

        self.status_frame = QFrame()
        self.status_frame.setObjectName('statusBar')
        s_lay = QVBoxLayout(self.status_frame)
        s_lay.setContentsMargins(0, 0, 0, 0)
        s_lay.setSpacing(0)
        self.progress = ProgressBar()
        s_lay.addWidget(self.progress)

        tel_row = QHBoxLayout()
        tel_row.setContentsMargins(14, 8, 14, 9)
        tel_row.setSpacing(16)
        rem_w, self.lbl_rem_title, self.lbl_rem = make_stat('Remaining', 'statHero')
        ela_w, self.lbl_ela_title, self.lbl_ela = make_stat('Elapsed', 'statValue')
        sld_w, _, self.lbl_slide = make_stat('Slide', 'statValue')
        clk_w, _, self.lbl_clock = make_stat('Clock', 'statMuted')

        self.lbl_jump = QLabel()
        self.lbl_jump.setObjectName('jumpBadge')
        self.lbl_jump.hide()
        self.lbl_blank = QLabel()
        self.lbl_blank.hide()
        self.lbl_mode = QLabel()
        self.lbl_mode.setObjectName('modePill')
        self.lbl_mode.setTextFormat(Qt.TextFormat.RichText)

        tel_row.addWidget(rem_w)
        tel_row.addWidget(make_vsep())
        tel_row.addWidget(ela_w)
        tel_row.addWidget(make_vsep())
        tel_row.addWidget(sld_w)
        tel_row.addWidget(make_vsep())
        tel_row.addWidget(clk_w)
        tel_row.addStretch(1)
        tel_row.addWidget(self.lbl_jump, 0, Qt.AlignmentFlag.AlignVCenter)
        tel_row.addWidget(self.lbl_blank, 0, Qt.AlignmentFlag.AlignVCenter)
        tel_row.addWidget(self.lbl_mode, 0, Qt.AlignmentFlag.AlignVCenter)
        s_lay.addLayout(tel_row)

        # Quiet bottom strip
        footer_bar = QFrame()
        footer_bar.setObjectName('footerBar')
        footer_bar.setFixedHeight(28)
        footer = QHBoxLayout(footer_bar)
        footer.setContentsMargins(12, 0, 8, 0)
        footer.setSpacing(6)
        self.help_bar = QLabel('←/→ Slides   Shift+↵ Back   N+↵ Jump   G Overview   S Timer   B/W Blank   X Swap   Alt+1–3 Layout')
        self.help_bar.setStyleSheet('background: transparent; color: #5e5e65; font-size: 11px;')

        self.layout_btns = {}
        for lid, tip in ((1, 'Layout 1: Side notes (Alt+1)'),
                         (2, 'Layout 2: Bottom notes (Alt+2)'),
                         (3, 'Layout 3: Slides only (Alt+3)')):
            b = QPushButton()
            b.setObjectName('toolBtn')
            b.setIcon(make_layout_icon(lid))
            b.setIconSize(QSize(16, 12))
            b.setFixedSize(28, 20)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _, n=lid: self.set_layout(n))
            self.layout_btns[lid] = b

        self.btn_swap_layout = QPushButton('Swap')
        self.btn_swap_layout.setObjectName('toolBtn')
        self.btn_swap_layout.setIcon(make_layout_icon('swap'))
        self.btn_swap_layout.setIconSize(QSize(14, 11))
        self.btn_swap_layout.setToolTip('Swap slides and speaker notes position')
        self.btn_swap_layout.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_swap_layout.clicked.connect(self.toggle_layout_swap)

        f_sep = QFrame()
        f_sep.setObjectName('vSep')
        f_sep.setFixedHeight(14)

        btn_grid = QPushButton('Overview')
        btn_grid.setObjectName('toolBtn')
        btn_grid.setToolTip('Slide overview (G)')
        btn_grid.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_grid.clicked.connect(self.toggle_overview)
        btn_help = QPushButton('Shortcuts')
        btn_help.setObjectName('toolBtn')
        btn_help.setToolTip('Keyboard shortcuts (?)')
        btn_help.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_help.clicked.connect(self.toggle_help)

        footer.addWidget(self.help_bar, 1)
        for lid in (1, 2, 3):
            footer.addWidget(self.layout_btns[lid])
        footer.addWidget(self.btn_swap_layout)
        footer.addWidget(f_sep)
        footer.addWidget(btn_grid)
        footer.addWidget(btn_help)

        self.body = QWidget()
        self.body.setObjectName('paneGrid')
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addWidget(self.body, 1)
        main.addWidget(footer_bar)
        self.set_layout(layout)

        self.movies = find_movies(path, self.split)
        self.player, self.movie = QMediaPlayer(self), None   # movie: (rect, path) currently loaded
        self.player.setAudioOutput(QAudioOutput(self))
        self.player.setVideoSink(QVideoSink(self))
        self.player.videoSink().videoFrameChanged.connect(self.on_frame)

        # video controls (shown only on pages with a \\movie); NoFocus keeps arrow keys for slides
        self.vbar = QFrame()
        self.vbar.setObjectName('vbar')
        self.vbar.setFixedHeight(38)
        hb = QHBoxLayout(self.vbar)
        hb.setContentsMargins(12, 0, 12, 0)
        hb.setSpacing(8)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.vtime = QLabel('0:00 / 0:00')
        self.vtime.setStyleSheet('color: #84848c; font-family: monospace; font-size: 12px; background: transparent;')
        self.btn_play = QPushButton('Play')
        btns = [(self.btn_play, self.play_pause), (QPushButton('-5s'), lambda: self.skip(-5000)),
                (QPushButton('+5s'), lambda: self.skip(5000)), (QPushButton('Fullscreen'), self.toggle_full)]
        for b, f in btns:
            b.setObjectName('toolBtn')
        for b, f in btns[:3]:
            hb.addWidget(b)
        hb.addWidget(self.seek, 1)
        hb.addWidget(self.vtime)
        hb.addWidget(btns[3][0])
        for b, f in btns:
            b.clicked.connect(f)
        for wdg in (self.seek, *(b for b, _ in btns)):
            wdg.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.seek.sliderMoved.connect(self.seek_to)
        self.seek.mousePressEvent = self.on_seek_press
        self.player.durationChanged.connect(lambda d: self.seek.setRange(0, d))
        self.player.positionChanged.connect(self.on_position)
        self.player.playbackStateChanged.connect(
            lambda st: self.btn_play.setText('Pause' if st == QMediaPlayer.PlaybackState.PlayingState else 'Play'))
        self.layout().insertWidget(1, self.vbar)

        self.help_overlay = HelpOverlay(self)
        self.overview = OverviewOverlay(self)

        self.aud = Audience(self)
        self.aud.annotations = self.annotations
        screens = QGuiApplication.screens()
        self.aud_screen_idx = 1 if len(screens) > 1 else 0
        if len(screens) > 1:
            self.aud.setGeometry(screens[1].geometry())
            self.aud.showFullScreen()
        else:
            self.aud.resize(1280, 720)
            self.aud.show()
        self.resize(1440, 880)
        self.show()

        t = QTimer(self, interval=250)
        t.timeout.connect(self.tick)
        t.start()
        self.go(0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.help_overlay.isVisible():
            self.help_overlay.setGeometry(self.rect())
        if self.overview.isVisible():
            self.overview.setGeometry(self.rect())

    # --- navigation ---
    def go(self, n):
        n = max(0, min(self.doc.pageCount() - 1, n))
        if n != self.n:
            self.stop_video()
            self.drawing_stroke = None
            self.erasing = False
            if self.movies.get(n):                  # preload so the seek bar knows the duration
                self.load_video(self.movies[n][0])
        self.n = n
        if n and self.since is None and self.acc == 0:
            self.since = time.monotonic()           # first move starts the clock
        self.cur.page = self.aud.page = self.n
        frame, ov = self.keys[self.n] if self.n < len(self.keys) else (str(self.n + 1), 1)
        self.cur_card._meta_label.setText(f'Frame {frame}' + (f' · click {ov}' if ov > 1 else ''))
        if self.n + 1 < self.doc.pageCount():
            nf, nov = self.keys[self.n + 1] if self.n + 1 < len(self.keys) else (str(self.n + 2), 1)
            self.next_card._meta_label.setText(f'Frame {nf}' + (f' · click {nov}' if nov > 1 else ''))
        else:
            self.next_card._meta_label.setText('End of deck')
        if self.notes_path:
            self.show_notes()
        else:
            self.notes.page = self.n
        self.vbar.setVisible(bool(self.movies.get(self.n)))
        self.next.page = self.n + 1
        for v in (self.cur, self.next, self.notes, self.aud):
            v.update()
        self.tick()
        QTimer.singleShot(30, self.prefetch)

    def prefetch(self):
        """Warm the LRU cache for adjacent pages so slide transitions feel instant."""
        for p in (self.n + 1, self.n + 2, self.n - 1):
            if 0 <= p < self.doc.pageCount():
                for view in (self.cur, self.aud):
                    r = view.target()
                    if r is not None:
                        self.doc.render_half(p, view.half, self.split, r.width(), r.height(), view.devicePixelRatioF())

    def resolve_jump(self, query):
        """Parse '4', '4.2', 'B1', or 'p12' into a 0-based page index."""
        q = query.strip()
        if not q:
            return None
        if q.lower().startswith('p') and q[1:].isdigit():
            idx = int(q[1:]) - 1
            return idx if 0 <= idx < self.doc.pageCount() else None
        q_up = q.upper()
        if '.' in q_up:
            f, _, o = q_up.partition('.')
            if o.isdigit():
                for i, k in enumerate(self.keys):
                    if k == (f, int(o)):
                        return i
        for i, k in enumerate(self.keys):
            if k[0].upper() == q_up:
                return i
        if q.isdigit():
            idx = int(q) - 1
            return idx if 0 <= idx < self.doc.pageCount() else None
        return None

    def prompt_jump(self):
        text, ok = QInputDialog.getText(self, 'Jump to slide', 'Frame (e.g. 4, 4.2, B1) or page (p12):')
        if ok:
            idx = self.resolve_jump(text)
            if idx is not None:
                self.go(idx)

    def on_wheel(self, e):
        dy = e.angleDelta().y()
        if dy != 0:
            self.go(self.n + (1 if dy < 0 else -1))

    # --- Markdown notes ---
    def reload_notes(self):
        try:
            self.md = load_notes(self.notes_path)
        except OSError:
            self.md = []            # editors may delete+rewrite; the next change event reloads
        if self.notes_path not in self.watcher.files():
            self.watcher.addPath(self.notes_path)   # re-watch after an atomic save (rename)
        if self.n >= 0:
            self.show_notes()

    def show_notes(self):
        frame, ov = self.keys[self.n] if self.n < len(self.keys) else (str(self.n + 1), 1)
        md = notes_for(self.md, (frame, ov))
        if md.strip():
            self.notes.setMarkdown(md)
            style_notes_document(self.notes.document(), self.note_font_px)
        else:
            self.notes.setHtml(
                '<p style="color:#5e5e66;font-style:italic;margin:12px;">No speaker notes for this slide.</p>'
            )

    def adjust_note_font(self, delta):
        if not self.notes_path:
            return
        self.note_font_px = max(12, min(40, self.note_font_px + delta))
        self.notes.document().setDefaultStyleSheet(notes_css(self.note_font_px))
        self.show_notes()

    # --- presenter layout ---
    def _refresh_layout_buttons(self):
        for lid, btn in self.layout_btns.items():
            name = 'toolBtnActive' if lid == self.layout_no else 'toolBtn'
            if btn.objectName() != name:
                btn.setObjectName(name)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        sname = 'toolBtnActive' if self.layout_swapped else 'toolBtn'
        if self.btn_swap_layout.objectName() != sname:
            self.btn_swap_layout.setObjectName(sname)
            self.btn_swap_layout.style().unpolish(self.btn_swap_layout)
            self.btn_swap_layout.style().polish(self.btn_swap_layout)

    def toggle_layout_swap(self):
        self.set_layout(self.layout_no, swapped=not self.layout_swapped)

    def set_layout(self, n, swapped=None):
        """1: current | next over notes.  2: current | next, big notes below.  3: current | next, no notes."""
        if swapped is not None:
            self.layout_swapped = swapped
        old, self.body = self.body, QWidget()   # widgets move into the new container when added
        self.body.setObjectName('paneGrid')
        if n == 1:
            slide_col, notes_col = QVBoxLayout(), QVBoxLayout()
            slide_col.setSpacing(1)
            notes_col.setSpacing(1)
            slide_col.addWidget(self.cur_card, 1)
            slide_col.addWidget(self.status_frame)
            notes_col.addWidget(self.next_card, 2)
            notes_col.addWidget(self.notes_card, 5)
            g = QHBoxLayout(self.body)
            g.setSpacing(1)
            if self.layout_swapped:
                g.addLayout(notes_col, 9)
                g.addLayout(slide_col, 11)
            else:
                g.addLayout(slide_col, 11)
                g.addLayout(notes_col, 9)
        else:
            slides_row = QHBoxLayout()
            slides_row.setSpacing(1)
            if n == 3 and self.layout_swapped:
                slides_row.addWidget(self.next_card)
                slides_row.addWidget(self.cur_card)
            else:
                slides_row.addWidget(self.cur_card)
                slides_row.addWidget(self.next_card)
            g = QVBoxLayout(self.body)
            g.setSpacing(1)
            if n == 2 and self.layout_swapped:
                g.addWidget(self.notes_card, 5)
                g.addLayout(slides_row, 4)
            else:
                g.addLayout(slides_row, 4 if n == 2 else 1)
                g.addWidget(self.notes_card, 5)
            g.addWidget(self.status_frame)
        g.setContentsMargins(0, 0, 0, 0)
        self.notes_card.setVisible(n != 3)
        self.layout().replaceWidget(old, self.body)
        old.deleteLater()
        self.layout_no = n
        self._refresh_layout_buttons()

    def swap_screens(self):
        screens = QGuiApplication.screens()
        if len(screens) < 2:
            self.aud.showNormal() if self.aud.isFullScreen() else self.aud.showFullScreen()
            return
        self.aud_screen_idx = (self.aud_screen_idx + 1) % len(screens)
        pres_idx = (self.aud_screen_idx + 1) % len(screens)
        was_full = self.isFullScreen()
        self.aud.showNormal()
        self.aud.setGeometry(screens[self.aud_screen_idx].geometry())
        self.aud.showFullScreen()
        self.showNormal()
        self.setGeometry(screens[pres_idx].availableGeometry())
        if was_full:
            self.showFullScreen()
        else:
            self.showMaximized()

    def toggle_help(self):
        if self.overview.isVisible():
            self.overview.close_overlay()
        if self.help_overlay.isVisible():
            self.help_overlay.hide()
        else:
            self.help_overlay.setGeometry(self.rect())
            self.help_overlay.show()
            self.help_overlay.raise_()

    def toggle_overview(self):
        if self.help_overlay.isVisible():
            self.help_overlay.hide()
        if self.overview.isVisible():
            self.overview.close_overlay()
        else:
            self.overview.open_overlay()

    # --- video ---
    # Loaded-but-stopped shows the PDF poster; frames are drawn once playing or paused.
    def load_video(self, movie):
        self.movie = movie
        if os.path.exists(movie[1]):
            self.player.setSource(QUrl.fromLocalFile(movie[1]))
        else:
            self.vtime.setText('missing: ' + os.path.basename(movie[1]))

    def stopped(self):
        return self.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState

    def toggle_video(self, movie):
        if movie != self.movie:
            self.stop_video()
            self.load_video(movie)
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def play_pause(self):
        if self.movie:
            self.toggle_video(self.movie)

    def seek_to(self, ms):
        if not self.movie:
            return
        if self.stopped():
            self.player.pause()                     # paused state renders the frame at the new position
        self.player.setPosition(max(0, min(self.player.duration(), int(ms))))

    def skip(self, ms):
        self.seek_to(self.player.position() + ms)

    def on_seek_press(self, e):
        # jump to the clicked spot (default QSlider only pages by a step), then allow dragging
        sl = self.seek
        v = QStyle.sliderValueFromPosition(sl.minimum(), sl.maximum(), int(e.position().x()), sl.width())
        sl.setValue(v)
        self.seek_to(v)
        QSlider.mousePressEvent(sl, e)

    def toggle_full(self):
        if self.movie:
            if self.stopped():
                self.player.play()
            self.cur.full = self.aud.full = not self.aud.full
            self.cur.update()
            self.aud.update()

    def on_position(self, ms):
        if not self.seek.isSliderDown():
            self.seek.setValue(ms)
        self.vtime.setText(f'{fmt(ms / 1000)} / {fmt(self.player.duration() / 1000)}')

    def stop_video(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self.movie = self.cur.frame = self.aud.frame = None
        self.cur.full = self.aud.full = False
        self.seek.setValue(0)
        self.vtime.setText('0:00 / 0:00')
        self.cur.update()
        self.aud.update()

    def on_frame(self, f):
        if self.movie is None or not f.isValid() or self.stopped():
            return
        self.cur.frame = self.aud.frame = (self.movie[0], f.toImage())
        self.cur.update()
        self.aud.update()

    # --- pointer & pen annotations ---
    @staticmethod
    def _pt_seg_dist2(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return (px - ax) ** 2 + (py - ay) ** 2
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        cx, cy = ax + t * dx, ay + t * dy
        return (px - cx) ** 2 + (py - cy) ** 2

    def _slide_coords(self, pos):
        r = self.cur.target()
        if r is None or r.width() <= 0 or r.height() <= 0:
            return None
        rx, ry = (pos.x() - r.x()) / r.width(), (pos.y() - r.y()) / r.height()
        return (rx, ry) if 0 <= rx <= 1 and 0 <= ry <= 1 else None

    def erase_at(self, pt, radius=0.025):
        strokes = self.annotations.get(self.n)
        if not strokes:
            return False
        px, py = pt
        r2 = radius * radius
        hit = []
        for idx, (_, pts) in enumerate(strokes):
            if not pts:
                continue
            if len(pts) == 1:
                if (px - pts[0][0]) ** 2 + (py - pts[0][1]) ** 2 <= r2:
                    hit.append(idx)
            else:
                for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                    if self._pt_seg_dist2(px, py, ax, ay, bx, by) <= r2:
                        hit.append(idx)
                        break
        if not hit:
            return False
        for idx in reversed(hit):
            removed = strokes.pop(idx)
            self.undo_stack.append(('erase', self.n, idx, removed))
        self.cur.update()
        self.aud.update()
        return True

    def on_press(self, e):
        pt = self._slide_coords(e.position())
        if e.button() == Qt.MouseButton.RightButton and self.mode in ('pen', 'eraser'):
            if pt is not None:
                self.erasing = True
                self.erase_at(pt)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.cur.full:
            self.play_pause()
            return
        if pt is None:
            return
        if self.mode == 'eraser':
            self.erasing = True
            self.erase_at(pt)
            return
        if self.mode == 'pen':
            stroke = (PEN_COLORS[self.pen_idx][1], [pt])
            self.annotations.setdefault(self.n, []).append(stroke)
            self.undo_stack.append(('add', self.n, stroke))
            self.drawing_stroke = stroke
            self.cur.update()
            self.aud.update()
            return
        qpt = QPointF(*pt)
        for m in self.movies.get(self.n, []):
            if m[0].contains(qpt):
                self.toggle_video(m)
                return

    def on_release(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.drawing_stroke = None
            self.erasing = False
        elif e.button() == Qt.MouseButton.RightButton:
            self.erasing = False

    def on_move(self, e):
        pt = self._slide_coords(e.position())
        if self.erasing and pt is not None:
            self.erase_at(pt)
        elif self.drawing_stroke is not None and pt is not None:
            self.drawing_stroke[1].append(pt)
            self.cur.update()
            self.aud.update()
        self.set_pointer(pt)

    def set_pointer(self, pt):
        color = PEN_COLORS[self.pen_idx][1]
        self.aud.pointer, self.aud.mode, self.aud.pen_color = pt, self.mode, color
        self.cur.mode, self.cur.pen_color = self.mode, color
        self.cur.pointer = pt if self.mode == 'eraser' else None
        self.cur.update()
        self.aud.update()

    def _refresh_tool_buttons(self):
        for btn, active in ((self.btn_pen, self.mode == 'pen'), (self.btn_eraser, self.mode == 'eraser')):
            name = 'toolBtnActive' if active else 'toolBtn'
            if btn.objectName() != name:
                btn.setObjectName(name)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        cname, chex = PEN_COLORS[self.pen_idx]
        self.btn_color.setStyleSheet(f'color: {chex};')
        self.btn_color.setToolTip(f'Pen color: {cname} (P to cycle)')

    def cycle_pen_color(self):
        self.pen_idx = (self.pen_idx + 1) % len(PEN_COLORS)
        self.set_pointer(self.aud.pointer)
        self.tick()

    def toggle_pen(self):
        self.mode = 'laser' if self.mode == 'pen' else 'pen'
        self.set_pointer(self.aud.pointer)
        self.tick()

    def toggle_eraser(self):
        self.mode = 'pen' if self.mode == 'eraser' else 'eraser'
        self.set_pointer(self.aud.pointer)
        self.tick()

    def undo_stroke(self):
        while self.undo_stack:
            act = self.undo_stack.pop()
            kind = act[0]
            if kind == 'add':
                _, page, stroke = act
                strokes = self.annotations.get(page)
                if strokes and stroke in strokes:
                    strokes.remove(stroke)
                    break
            elif kind == 'erase':
                _, page, idx, stroke = act
                strokes = self.annotations.setdefault(page, [])
                strokes.insert(min(idx, len(strokes)), stroke)
                break
            elif kind == 'clear':
                _, snapshot = act
                for page, prev in snapshot.items():
                    self.annotations.setdefault(page, []).extend(prev)
                break
        self.cur.update()
        self.aud.update()

    def clear_strokes(self, all_pages=False):
        if all_pages:
            snapshot = {p: list(s) for p, s in self.annotations.items() if s}
            if snapshot:
                self.undo_stack.append(('clear', snapshot))
                self.annotations.clear()
        else:
            prev = self.annotations.pop(self.n, None)
            if prev:
                self.undo_stack.append(('clear', {self.n: list(prev)}))
        self.cur.update()
        self.aud.update()

    # --- timer ---
    def elapsed(self):
        return self.acc + (time.monotonic() - self.since if self.since is not None else 0)

    def tick(self):
        e = self.elapsed()
        r = self.dur - e
        total = max(1, self.doc.pageCount())
        slide_frac = (self.n + 1) / total
        time_frac = (e / self.dur) if self.dur > 0 else 1.0
        self.progress.set_progress(slide_frac, time_frac)

        rem_color = '#d9483b' if r < 0 else ('#d4912a' if r < min(180, self.dur * 0.15) else '#ecebea')
        self.lbl_rem.setText(fmt(r))
        self.lbl_rem.setStyleSheet(f'color: {rem_color};')

        paused = self.since is None and e > 0
        self.lbl_ela_title.setText('Paused' if paused else 'Elapsed')
        self.lbl_ela_title.setStyleSheet('color: #d4912a;' if paused else '')
        self.lbl_ela.setText(fmt(e))
        self.lbl_slide.setText(f'{self.n + 1} / {total}')
        self.lbl_clock.setText(datetime.now().strftime('%H:%M'))

        if self.mode == 'pen':
            dot_color = PEN_COLORS[self.pen_idx][1]
            mode_txt = f'Pen · {PEN_COLORS[self.pen_idx][0]}'
        elif self.mode == 'laser':
            dot_color, mode_txt = '#d9483b', 'Laser'
        elif self.mode == 'pointer':
            dot_color, mode_txt = '#d4912a', 'Pointer'
        elif self.mode == 'eraser':
            dot_color, mode_txt = '#b4b4bc', 'Eraser'
        else:
            dot_color, mode_txt = '#4e4e56', 'Off'
        dot = '○' if self.mode == 'off' else '●'
        self.lbl_mode.setText(f'<span style="color:{dot_color};">{dot}</span>&nbsp;&nbsp;{mode_txt}')
        self._refresh_tool_buttons()

        if self.aud.blank == 'black':
            self.lbl_blank.setObjectName('blankBadgeBlack')
            self.lbl_blank.setText('Blackout')
            self.lbl_blank.style().unpolish(self.lbl_blank)
            self.lbl_blank.style().polish(self.lbl_blank)
            self.lbl_blank.show()
        elif self.aud.blank == 'white':
            self.lbl_blank.setObjectName('blankBadgeWhite')
            self.lbl_blank.setText('Whiteout')
            self.lbl_blank.style().unpolish(self.lbl_blank)
            self.lbl_blank.style().polish(self.lbl_blank)
            self.lbl_blank.show()
        else:
            self.lbl_blank.hide()

    def _update_jump_badge(self):
        if self.jump_buf:
            self.lbl_jump.setText(f'Go {self.jump_buf} ↵')
            self.lbl_jump.show()
        else:
            self.lbl_jump.hide()

    # --- keys (shared by both windows) ---
    def keyPressEvent(self, e):
        self.key(e, self)

    def key(self, e, win):
        k, K = e.key(), Qt.Key
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        if k in (K.Key_Control, K.Key_Shift, K.Key_Alt, K.Key_Meta, K.Key_AltGr, K.Key_Super_L, K.Key_Super_R):
            return

        if self.help_overlay.isVisible():
            if k in (K.Key_Escape, K.Key_Question, K.Key_H):
                self.help_overlay.hide()
            return
        if self.overview.isVisible():
            if k in (K.Key_Escape, K.Key_G):
                self.overview.close_overlay()
            return

        # num + Enter quick slide jump
        if not alt and not ctrl and K.Key_0 <= k <= K.Key_9:
            self.jump_buf += chr(ord('0') + (k - K.Key_0))
            self._update_jump_badge()
            return
        if self.jump_buf:
            if k == K.Key_Period and not ctrl and not alt and '.' not in self.jump_buf:
                self.jump_buf += '.'
                self._update_jump_badge()
                return
            if k == K.Key_Backspace:
                self.jump_buf = self.jump_buf[:-1]
                self._update_jump_badge()
                return
            if k == K.Key_Escape:
                self.jump_buf = ''
                self._update_jump_badge()
                return
            if k in (K.Key_Return, K.Key_Enter) and not shift:
                q, self.jump_buf = self.jump_buf, ''
                self._update_jump_badge()
                idx = self.resolve_jump(q)
                if idx is not None:
                    self.go(idx)
                return
            self.jump_buf = ''
            self._update_jump_badge()

        if ctrl and k in (K.Key_Plus, K.Key_Equal):
            self.adjust_note_font(2)
        elif ctrl and k == K.Key_Minus:
            self.adjust_note_font(-2)
        elif ctrl and k == K.Key_G:
            self.prompt_jump()
        elif ctrl and k == K.Key_Z:
            self.undo_stroke()
        elif k in (K.Key_Return, K.Key_Enter):
            self.go(self.n - 1 if shift else self.n + 1)
        elif k in (K.Key_Right, K.Key_Down, K.Key_PageDown, K.Key_Space, K.Key_J):
            self.go(self.n + 1)
        elif k in (K.Key_Left, K.Key_Up, K.Key_PageUp, K.Key_Backspace, K.Key_K):
            self.go(self.n - 1)
        elif k == K.Key_Home:
            self.go(0)
        elif k == K.Key_End:
            self.go(self.doc.pageCount() - 1)
        elif k == K.Key_G:
            self.toggle_overview()
        elif k == K.Key_Colon:
            self.prompt_jump()
        elif k in (K.Key_Question, K.Key_H):
            self.toggle_help()
        elif k == K.Key_L:
            self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
            self.set_pointer(self.aud.pointer)
            self.tick()
        elif k == K.Key_D:
            self.toggle_pen()
        elif k == K.Key_E:
            self.toggle_eraser()
        elif k == K.Key_P:
            self.pen_idx = (self.pen_idx + 1) % len(PEN_COLORS)
            self.set_pointer(self.aud.pointer)
            self.tick()
        elif k == K.Key_U:
            self.undo_stroke()
        elif k == K.Key_C:
            self.clear_strokes(all_pages=shift)
        elif k in (K.Key_B, K.Key_Period):
            self.aud.blank = None if self.aud.blank == 'black' else 'black'
            self.aud.update()
            self.tick()
        elif k in (K.Key_W, K.Key_Comma):
            self.aud.blank = None if self.aud.blank == 'white' else 'white'
            self.aud.update()
            self.tick()
        elif k == K.Key_X:
            self.swap_screens()
        elif k == K.Key_S:
            if self.since is None:
                self.since = time.monotonic()
            else:
                self.acc += time.monotonic() - self.since
                self.since = None
            self.tick()
        elif k == K.Key_R:
            self.since, self.acc = None, 0.0
            self.tick()
        elif k in (K.Key_Plus, K.Key_Equal):
            self.dur += 60
            self.tick()
        elif k in (K.Key_Minus, K.Key_Underscore):
            self.dur -= 60
            self.tick()
        elif k == K.Key_T:
            text, ok = QInputDialog.getText(self, 'Remaining time', 'Remaining (min, m:ss or h:mm:ss):',
                                            text=fmt(self.dur - self.elapsed()))
            try:
                if ok:
                    self.dur = self.elapsed() + parse_time(text)
                    self.tick()
            except ValueError:
                pass
        elif k == K.Key_V:
            self.play_pause()
        elif k in (K.Key_BracketLeft, K.Key_BracketRight):
            self.skip(-5000 if k == K.Key_BracketLeft else 5000)
        elif k == K.Key_Z:
            self.toggle_full()
        elif alt and not ctrl and k in (K.Key_1, K.Key_2, K.Key_3):
            self.set_layout(k - K.Key_0)
        elif k == K.Key_F:
            win.showNormal() if win.isFullScreen() else win.showFullScreen()
        elif k == K.Key_Escape and win.isFullScreen():
            win.showNormal()
        elif k == K.Key_Q:
            QApplication.quit()

    def closeEvent(self, _):
        QApplication.quit()


class NotesHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Beamer Markdown speaker notes."""

    def __init__(self, doc):
        super().__init__(doc)

        def fmt_of(color, bold=False, italic=False, bg=None):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            if italic:
                f.setFontItalic(True)
            if bg:
                f.setBackground(QColor(bg))
            return f

        self.f_slide_head = fmt_of('#e26458', bold=True)
        self.f_subhead = fmt_of('#f4f3ef', bold=True)
        self.f_bold = fmt_of('#f5f5f3', bold=True)
        self.f_italic = fmt_of('#b4b4bc', italic=True)
        self.f_code = fmt_of('#d8a657', bg='#1e1e22')
        self.f_fence = fmt_of('#9a9aa2')
        self.f_bullet = fmt_of('#7d7d86', bold=True)
        self.f_quote = fmt_of('#8e8e96', italic=True)
        self.f_comment = fmt_of('#5a5a62', italic=True)

        self.rules = [
            (re.compile(r'<!--.*?-->'), self.f_comment),
            (re.compile(r'^#{2,6}\s+.*'), self.f_subhead),
            (re.compile(r'^\s*>\s.*'), self.f_quote),
            (re.compile(r'^\s*(?:[-*+]|\d+\.)\s'), self.f_bullet),
            (re.compile(r'`[^`]+`'), self.f_code),
            (re.compile(r'\*\*[^*]+\*\*|__[^_]+__'), self.f_bold),
            (re.compile(r'(?<!\*)\*[^*]+\*(?!\*)'), self.f_italic),
        ]

    def highlightBlock(self, text):
        in_fence = self.previousBlockState() == 1
        if text.lstrip().startswith(('```', '~~~')):
            self.setFormat(0, len(text), self.f_fence)
            self.setCurrentBlockState(0 if in_fence else 1)
            return
        if in_fence:
            self.setFormat(0, len(text), self.f_fence)
            self.setCurrentBlockState(1)
            return
        self.setCurrentBlockState(0)
        if HEAD_RE.match(text):
            self.setFormat(0, len(text), self.f_slide_head)
            return
        for rx, cf in self.rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), cf)


class EmacsEdit(QPlainTextEdit):
    """QPlainTextEdit with the usual Emacs keys. Plain typing and IME input are left to Qt.
    cmds: window commands - save, quit, search(backward), next, prev, note, message(text)."""

    def __init__(self, cmds):
        super().__init__()
        self.cmds, self.mark, self.prefix, self.last_kill = cmds, False, None, False

    def move(self, op, n=1):
        c = self.textCursor()
        c.movePosition(op, QTextCursor.MoveMode.KeepAnchor if self.mark else QTextCursor.MoveMode.MoveAnchor, n)
        self.setTextCursor(c)

    def kill(self, c, append=False):
        text = c.selectedText().replace('\u2029', '\n')      # Qt's paragraph separator
        cb = QApplication.clipboard()
        cb.setText(cb.text() + text if append else text)
        c.removeSelectedText()
        self.setTextCursor(c)
        self.last_kill = True

    def deactivate(self):
        c = self.textCursor()
        c.clearSelection()
        self.setTextCursor(c)
        self.mark = False

    def keyPressEvent(self, e):
        K, Op, M = Qt.Key, QTextCursor.MoveOperation, Qt.KeyboardModifier
        ctrl, alt, k = bool(e.modifiers() & M.ControlModifier), bool(e.modifiers() & M.AltModifier), e.key()
        if k in (K.Key_Control, K.Key_Shift, K.Key_Alt, K.Key_Meta, K.Key_AltGr, K.Key_Super_L, K.Key_Super_R):
            return super().keyPressEvent(e)       # a bare modifier must not end C-x/C-c or a C-k run
        was_kill, self.last_kill = self.last_kill, False
        page = max(1, self.viewport().height() // self.fontMetrics().lineSpacing() - 2)
        if self.prefix:                                       # second key of C-x / C-c
            prefix, self.prefix = self.prefix, None
            self.cmds['message']('')
            cmd = {('C-x', True, K.Key_S): 'save', ('C-x', True, K.Key_C): 'quit',
                   ('C-c', True, K.Key_J): 'note', ('C-c', True, K.Key_N): 'next',
                   ('C-c', True, K.Key_P): 'prev'}.get((prefix, ctrl, k))
            if cmd:
                self.cmds[cmd]()
            elif prefix == 'C-x' and k == K.Key_H:
                self.selectAll()
            elif prefix == 'C-x' and k == K.Key_U:
                self.undo()
            return
        if ctrl and not alt:
            moves = {K.Key_F: Op.NextCharacter, K.Key_B: Op.PreviousCharacter, K.Key_N: Op.Down,
                     K.Key_P: Op.Up, K.Key_A: Op.StartOfBlock, K.Key_E: Op.EndOfBlock}
            if k in moves:
                self.move(moves[k])
            elif k == K.Key_V:
                self.move(Op.Down, page)
            elif k in (K.Key_X, K.Key_C):
                self.prefix = 'C-x' if k == K.Key_X else 'C-c'
                self.cmds['message'](self.prefix + '-')
            elif k == K.Key_D:
                self.textCursor().deleteChar()
            elif k == K.Key_K:
                c = self.textCursor()
                c.clearSelection()
                c.movePosition(Op.NextCharacter if c.atBlockEnd() else Op.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                self.kill(c, append=was_kill)
            elif k == K.Key_W:
                if self.textCursor().hasSelection():
                    self.kill(self.textCursor())
                self.mark = False
            elif k == K.Key_Y:
                self.deactivate()
                self.insertPlainText(QApplication.clipboard().text())
            elif k == K.Key_Space:
                self.deactivate()
                self.mark = True
                self.cmds['message']('Mark set')
            elif k == K.Key_G:
                self.deactivate()
                self.cmds['message']('Quit')
            elif k in (K.Key_Slash, K.Key_Underscore):
                self.undo()
            elif k == K.Key_Question:
                self.redo()
            elif k in (K.Key_S, K.Key_R):
                self.cmds['search'](k == K.Key_R)
            elif k == K.Key_L:
                self.centerCursor()
            elif k == K.Key_O:
                c = self.textCursor()
                c.insertText('\n')
                c.movePosition(Op.PreviousCharacter)
                self.setTextCursor(c)
            else:
                super().keyPressEvent(e)
            return
        if alt and not ctrl:
            if k == K.Key_F:
                self.move(Op.NextWord)
            elif k == K.Key_B:
                self.move(Op.PreviousWord)
            elif k == K.Key_V:
                self.move(Op.Up, page)
            elif k in (K.Key_Less, K.Key_Greater):
                self.move(Op.Start if k == K.Key_Less else Op.End)
            elif k == K.Key_W:
                QApplication.clipboard().setText(self.textCursor().selectedText().replace('\u2029', '\n'))
                self.deactivate()
            elif k in (K.Key_D, K.Key_Backspace):
                c = self.textCursor()
                c.clearSelection()
                c.movePosition(Op.EndOfWord if k == K.Key_D else Op.PreviousWord, QTextCursor.MoveMode.KeepAnchor)
                if k == K.Key_D and not c.hasSelection():      # at a word end: kill through the next word
                    c.movePosition(Op.NextWord, QTextCursor.MoveMode.KeepAnchor)
                    c.movePosition(Op.EndOfWord, QTextCursor.MoveMode.KeepAnchor)
                self.kill(c, append=was_kill)
            elif k in (K.Key_N, K.Key_P):
                self.cmds['next' if k == K.Key_N else 'prev']()
            else:
                super().keyPressEvent(e)
            return
        if self.mark and e.text():          # typing ends the region (no delete-selection)
            self.deactivate()
        super().keyPressEvent(e)


class NotesEditor(QWidget):
    """FOO.notes.md beside the slides of FOO.pdf. Moving in the text turns to that frame's
    page; M-n/M-p (or the mouse wheel on the slide) turn pages and scroll the text along."""

    def __init__(self, pdf, notes=None):
        super().__init__()
        try:
            self.doc = Pdf(pdf)
            assert self.doc.pageCount() > 0
        except Exception as e:
            QMessageBox.critical(None, 'Beamer Notes Editor', f'Cannot open {pdf}\n{e}')
            sys.exit(1)
        ps = self.doc.pagePointSize(0)
        self.keys = page_keys(pdf)
        self.path = notes or os.path.splitext(pdf)[0] + '.notes.md'
        self.page, self.syncing, self.last_sec, self.searching = -1, False, None, False

        self.view = SlideView(self.doc, ps.width() / ps.height() > 2.5)
        self.view.wheelEvent = lambda e: self.show_page(self.page + (1 if e.angleDelta().y() < 0 else -1), True)

        self.preview = QTextBrowser()
        self.preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview.document().setDefaultStyleSheet(notes_css(16))

        self.edit = EmacsEdit({'save': self.save, 'quit': self.close, 'search': self.search,
                               'next': lambda: self.show_page(self.page + 1, True),
                               'prev': lambda: self.show_page(self.page - 1, True),
                               'note': self.add_note, 'message': self.message})
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(12)
        self.edit.setFont(font)
        self.edit.setViewportMargins(12, 10, 12, 10)
        self.highlighter = NotesHighlighter(self.edit.document())

        self.mini = QLineEdit(readOnly=True)                  # echo area / I-search prompt
        self.mini.setObjectName('minibuffer')
        self.mini.installEventFilter(self)
        self.mini.textEdited.connect(self.search_update)
        if os.path.exists(self.path):
            with open(self.path, encoding='utf-8') as f:
                self.edit.setPlainText(f.read())

        nav_btns = []
        for label, tip, cb in (('Prev', 'Previous slide (M-p)', lambda: self.show_page(self.page - 1, True)),
                               ('Next', 'Next slide (M-n)', lambda: self.show_page(self.page + 1, True)),
                               ('+ Note', 'Insert or jump to note heading (C-c C-j)', self.add_note),
                               ('Swap', 'Swap slide and notes panes', self.swap_panes)):
            b = QPushButton(label)
            b.setObjectName('toolBtn')
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(cb)
            nav_btns.append(b)
        self.save_btn = QPushButton('Save')
        self.save_btn.setObjectName('saveBtn')
        self.save_btn.setToolTip('Save notes (C-x C-s)')
        self.save_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.save_btn.clicked.connect(self.save)

        self.slide_card = make_pane('Slide', self.view, nav_btns)
        preview_card = make_pane('Preview', self.preview)
        self.edit_card = make_pane(os.path.basename(self.path), self.edit, [self.save_btn])

        left_split = QSplitter(Qt.Orientation.Vertical)
        left_split.addWidget(self.slide_card)
        left_split.addWidget(preview_card)
        left_split.setSizes([520, 360])

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        rv.addWidget(self.edit_card, 1)
        rv.addWidget(self.mini)

        self.split = QSplitter()
        self.split.addWidget(left_split)
        self.split.addWidget(right)
        self.split.setSizes([660, 840])
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.split)

        self.edit.cursorPositionChanged.connect(self.on_cursor)
        self.edit.textChanged.connect(self.refresh)
        self.edit.document().modificationChanged.connect(self.set_title)
        self.edit.document().setModified(False)
        self.set_title(False)
        self.show_page(0, False)
        self.on_cursor()
        self.message('C-x C-s save   M-n / M-p page   C-c C-j add note   C-s search   C-x C-c quit')
        self.resize(1520, 920)
        self.show()
        self.edit.setFocus()

    def swap_panes(self):
        sizes = self.split.sizes()
        self.split.insertWidget(0, self.split.widget(1))
        self.split.setSizes(list(reversed(sizes)))

    def message(self, text):
        if not self.searching:
            self.mini.setText(text)

    def set_title(self, modified):
        self.setWindowTitle(('*' if modified else '') + os.path.basename(self.path) + ' — Beamer Notes Editor')
        self.edit_card._title_label.setText(os.path.basename(self.path))
        self.edit_card._meta_label.setText('Modified' if modified else '')
        self.edit_card._meta_label.setStyleSheet('color: #d9483b;' if modified else '')
        name = 'saveBtnDirty' if modified else 'saveBtn'
        if self.save_btn.objectName() != name:
            self.save_btn.setObjectName(name)
            self.save_btn.style().unpolish(self.save_btn)
            self.save_btn.style().polish(self.save_btn)

    # --- notes <-> pages ---
    def key(self):
        return self.keys[self.page] if self.page < len(self.keys) else (str(self.page + 1), 1)

    def refresh(self):
        md = notes_for(parse_notes(self.edit.toPlainText()), self.key())
        if md.strip():
            self.preview.setMarkdown(md)
            style_notes_document(self.preview.document(), 16)
        else:
            self.preview.setHtml(
                '<p style="color:#5e5e66;font-style:italic;margin:12px;">No notes for this page yet.</p>'
            )

    def section_at_cursor(self):
        """(frame, first click or None) of the heading above the cursor, ignoring code fences."""
        cur_num = self.edit.textCursor().blockNumber()
        last = None
        for b, m in iter_heading_blocks(self.edit.document()):
            if b.blockNumber() > cur_num:
                break
            last = (m[1], int(m[2]) if m[2] else None)
        return last

    def on_cursor(self):
        sec = self.section_at_cursor()
        if self.syncing or sec is None or sec == self.last_sec:
            return
        self.last_sec = sec
        pages = [i for i, k in enumerate(self.keys) if k == (sec[0], sec[1] or 1)] or \
                [i for i, k in enumerate(self.keys) if k[0] == sec[0]]
        if pages and pages[0] != self.page:
            self.show_page(pages[0], False)

    def section_block(self, key):
        """Heading block for key: its own click, else frame-wide, else any of the frame."""
        frame, ov = key
        exact = wide = anyb = None
        for b, m in iter_heading_blocks(self.edit.document()):
            if m[1] == frame:
                lo = int(m[2]) if m[2] else None
                hi = int(m[3]) if m[3] else lo
                if lo is None:
                    wide = wide or b
                elif lo <= ov <= hi:
                    exact = exact or b
                anyb = anyb or b
        return exact or wide or anyb

    def goto_block(self, b):
        self.syncing = True
        c = QTextCursor(b.next() if b.next().isValid() else b)
        self.edit.setTextCursor(c)
        self.edit.verticalScrollBar().setValue(b.blockNumber())
        self.syncing = False
        self.last_sec = self.section_at_cursor()

    def show_page(self, i, move_cursor):
        if not 0 <= i < self.doc.pageCount():
            return
        self.page = self.view.page = i
        self.view.update()
        frame, ov = self.key()
        self.slide_card._meta_label.setText(
            f'{i + 1} / {self.doc.pageCount()} · Frame {frame}' + (f'.{ov}' if ov > 1 else '')
        )
        self.refresh()
        if move_cursor:
            b = self.section_block((frame, ov))
            if b:
                self.goto_block(b)
            else:
                self.message(f'No notes for frame {frame}, click {ov} (C-c C-j adds them)')

    def add_note(self):
        """Go to the notes for this page, adding '# N' (or '# N.k') in order if missing."""
        frame, ov = self.key()
        b = self.section_block((frame, ov))
        if b:
            return self.goto_block(b)
        name = f'{frame}.{ov}' if sum(k[0] == frame for k in self.keys) > 1 else frame
        rank = lambda f, lo: (f.startswith('B'), int(f.lstrip('B')), lo or 0)   # noqa: E731
        new = rank(frame, ov if '.' in name else None)
        target = None
        for blk, m in iter_heading_blocks(self.edit.document()):
            if rank(m[1], int(m[2]) if m[2] else None) > new:
                target = blk
                break
        c = QTextCursor(self.edit.document())
        if target is not None:
            c.setPosition(target.position())
            c.insertText(f'# {name}\n\n\n')
        else:
            c.movePosition(QTextCursor.MoveOperation.End)
            c.insertText(('' if c.atBlockStart() else '\n') + f'\n# {name}\n\n')
        self.goto_block(self.section_block((frame, ov)))

    # --- files ---
    def save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(self.edit.toPlainText())
        self.edit.document().setModified(False)
        self.message('Wrote ' + self.path)

    def closeEvent(self, e):
        if self.edit.document().isModified():
            B = QMessageBox.StandardButton
            r = QMessageBox.question(self, 'Beamer Notes Editor', f'Save {os.path.basename(self.path)}?',
                                     B.Save | B.Discard | B.Cancel)
            if r == B.Cancel:
                return e.ignore()
            if r == B.Save:
                self.save()
        e.accept()

    # --- I-search in the echo area ---
    def search(self, backward):
        if self.searching:
            return self.search_step(backward)
        self.searching, self.backward, self.origin = True, backward, self.edit.textCursor()
        self.mini.setReadOnly(False)
        self.mini.clear()
        self.mini.setPlaceholderText('I-search backward:' if backward else 'I-search:')
        self.mini.setFocus()

    def find(self, start, backward):
        text = self.mini.text()
        F = QTextDocument.FindFlag
        flags = F(0) | (F.FindCaseSensitively if text != text.lower() else F(0)) | (F.FindBackward if backward else F(0))
        found = self.edit.document().find(text, start, flags)
        self.mini.setStyleSheet('' if not text or not found.isNull() else 'color: #d9483b;')
        if not found.isNull():
            self.edit.setTextCursor(found)

    def search_update(self, _):
        self.find(self.origin.selectionStart() if self.backward else self.origin.position(), self.backward)

    def search_step(self, backward):
        self.backward = backward
        c = self.edit.textCursor()
        self.find(c.selectionStart() if backward else c.selectionEnd(), backward)

    def search_end(self, cancel):
        c = QTextCursor(self.origin) if cancel else self.edit.textCursor()
        if not cancel:
            c.setPosition(c.selectionStart() if self.backward else c.selectionEnd())
        self.edit.setTextCursor(c)
        self.searching = False
        self.mini.setReadOnly(True)
        self.mini.setPlaceholderText('')
        self.mini.setStyleSheet('')
        self.mini.setText('Quit' if cancel else '')
        self.edit.setFocus()

    def eventFilter(self, obj, e):
        if obj is self.mini and self.searching and e.type() == QEvent.Type.KeyPress:
            ctrl, k = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier), e.key()
            if ctrl and k in (Qt.Key.Key_S, Qt.Key.Key_R):
                self.search_step(k == Qt.Key.Key_R)
                return True
            if (ctrl and k == Qt.Key.Key_G) or k == Qt.Key.Key_Escape:
                self.search_end(True)
                return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.search_end(False)
                return True
        return super().eventFilter(obj, e)


def main():
    ap = argparse.ArgumentParser(description='Beamer Presenter Lite')
    ap.add_argument('pdf', nargs='?')
    ap.add_argument('-d', '--duration', type=float, default=20, help='talk length in minutes (default 20)')
    ap.add_argument('-l', '--layout', type=int, choices=[1, 2, 3], default=1,
                    help='presenter layout: 1 current|next+notes, 2 big notes below, 3 no notes')
    ap.add_argument('-n', '--notes', help='Markdown speaker notes (default: <pdf name>.notes.md if present)')
    ap.add_argument('-e', '--edit', action='store_true', help='open the Markdown notes editor instead')
    ap.add_argument('--install-desktop', action='store_true', help='add a launcher to the desktop app menu')
    ap.add_argument('--uninstall-desktop', action='store_true', help='remove that launcher')
    a = ap.parse_args()
    if a.install_desktop or a.uninstall_desktop:
        return install_desktop(remove=a.uninstall_desktop)
    app = QApplication(sys.argv)
    app.setApplicationName('Beamer Notes Editor' if a.edit else 'Beamer Presenter Lite')
    app.setDesktopFileName('beamer-notes-editor' if a.edit else 'beamer-presenter-lite')
    app.setWindowIcon(make_icon(EDITOR_ICON_SVG if a.edit else PRESENTER_ICON_SVG))
    app.setStyleSheet(APP_QSS)
    path = a.pdf or QFileDialog.getOpenFileName(None, 'Open PDF', '', 'PDF (*.pdf)')[0]
    if not path:
        sys.exit(0)
    w = NotesEditor(path, a.notes) if a.edit else Presenter(path, a.duration, a.layout, a.notes)  # noqa: F841
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
