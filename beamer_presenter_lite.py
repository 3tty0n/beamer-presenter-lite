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

Keys (either window): Right/Space/PgDn next, Left/PgUp prev, Home/End,
L pointer mode (laser/pointer/off), B or . blackout, S start/pause timer, R reset timer,
T set remaining time (e.g. 12 or 12:30), +/- remaining ±1 min,
V or click on a video: play/pause \\movie (multimedia package), [ / ] video -/+5 s,
Z video fills the audience screen (controls bar appears on video pages),
1/2/3 presenter layout (1 current|next+notes, 2 current|next over big notes, 3 no notes),
F fullscreen, Q quit.  Hover over the current slide in the presenter window
to show the pointer on the audience screen.
"""
import argparse
import os
import re
import shutil
import sys
import time

import pypdfium2 as pdfium
from pypdf import PdfReader

from PyQt6.QtCore import QEvent, QFileSystemWatcher, QPointF, QRectF, QSize, QSizeF, Qt, QTimer, QUrl
from PyQt6.QtGui import (QColor, QFontDatabase, QGuiApplication, QImage, QPainter, QTextCursor, QTextDocument,
                          QPolygonF, QRadialGradient)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PyQt6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QTextBrowser,
                             QLineEdit, QPlainTextEdit, QPushButton, QSlider, QSplitter, QStyle,
                             QVBoxLayout, QWidget)

MODES = ['laser', 'pointer', 'off']


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
    """The few QPdfDocument calls we use, on pypdfium2 (PyPI's PyQt6 ships no QtPdf)."""

    def __init__(self, path):
        self.doc = pdfium.PdfDocument(path)

    def pageCount(self):
        return len(self.doc)

    def pagePointSize(self, i):
        return QSizeF(*self.doc[i].get_size())

    def render(self, i, size):
        page = self.doc[i]
        bm = page.render(scale=size.height() / page.get_size()[1], rev_byteorder=True, prefer_bgrx=True)
        return QImage(bytes(bm.buffer), bm.width, bm.height, bm.stride, QImage.Format.Format_RGBX8888).copy()


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


HEAD_RE = re.compile(r'#[ \t]+(B?\d+)(?:\.(\d+)(?:-(\d+))?)?(?=\s|$)(.*)')   # notes heading, see load_notes


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


def install_desktop(remove=False):
    """Write (or remove) a .desktop entry so the app shows up in the Linux app menu."""
    data = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    exe = shutil.which('beamer-presenter-lite') or os.path.abspath(sys.argv[0])
    for name, title, comment, arg in [
            ('beamer-presenter-lite', 'Beamer Presenter Lite',
             'Present beamer PDFs with speaker notes, pointer, timer and video', ''),
            ('beamer-notes-editor', 'Beamer Notes Editor',
             'Edit Markdown speaker notes beside the slides (Emacs keys)', ' --edit')]:
        path = os.path.join(data, 'applications', name + '.desktop')
        if remove:
            if os.path.exists(path):
                os.remove(path)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write(f'[Desktop Entry]\nType=Application\nName={title}\nComment={comment}\n'
                        f'Exec={exe}{arg} %f\nIcon=x-office-presentation\nTerminal=false\n'
                        'Categories=Office;Viewer;\nMimeType=application/pdf;\n')
        print(('removed ' if remove else 'wrote ') + path)


class SlideView(QWidget):
    """Draws one half (0 = slide, 1 = notes) of a PDF page, fitted and centered."""

    def __init__(self, doc, split, half=0, bg='#111'):
        super().__init__()
        self.doc, self.split, self.half, self.page = doc, split, half, 0
        self.pointer, self.mode = None, 'laser'   # pointer: (rx, ry) in 0..1 or None
        self.black = False
        self.frame = None                          # (QRectF 0..1, QImage) video frame overlay
        self.full = False                          # video frame fills the whole widget
        self._cache = (None, None)
        self.setStyleSheet(f'background:{bg}')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

    def target(self):
        """Rect where the slide image is drawn, or None if nothing to draw."""
        if not (0 <= self.page < self.doc.pageCount()) or (self.half and not self.split):
            return None
        ps = self.doc.pagePointSize(self.page)
        pw, ph = ps.width() / (2 if self.split else 1), ps.height()
        s = min(self.width() / pw, self.height() / ph)
        w, h = pw * s, ph * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def image(self, r):
        key = (self.page, self.half, int(r.width()), int(r.height()), self.devicePixelRatioF())
        if self._cache[0] != key:
            dpr = self.devicePixelRatioF()
            w, h = round(r.width() * dpr), round(r.height() * dpr)
            full = self.doc.render(self.page, QSize(w * (2 if self.split else 1), h))
            img = full.copy(self.half * w, 0, w, h)
            img.setDevicePixelRatio(dpr)
            self._cache = (key, img)
        return self._cache[1]

    def paintEvent(self, _):
        r = self.target()
        if r is None or self.black:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
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
        if self.pointer and self.mode != 'off':
            x, y = r.x() + self.pointer[0] * r.width(), r.y() + self.pointer[1] * r.height()
            if self.mode == 'laser':
                rad = max(8.0, r.width() / 120)
                g = QRadialGradient(QPointF(x, y), rad * 2)
                g.setColorAt(0, QColor(255, 0, 0, 255))
                g.setColorAt(0.4, QColor(255, 0, 0, 200))
                g.setColorAt(1, QColor(255, 0, 0, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(g)
                p.drawEllipse(QPointF(x, y), rad * 2, rad * 2)
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
        self.n, self.mode, self.dur = -1, 'laser', minutes * 60   # n = -1 until the first go()
        self.since, self.acc = None, 0.0           # timer: running start or None; banked seconds

        self.setWindowTitle(f'Presenter — {path}')
        self.setStyleSheet('background:#111; color:#eee')
        self.cur = SlideView(self.doc, self.split)
        self.cur.setMouseTracking(True)
        self.cur.setCursor(Qt.CursorShape.CrossCursor)
        self.cur.mouseMoveEvent = self.on_move
        self.cur.leaveEvent = lambda _: self.set_pointer(None)
        self.cur.mousePressEvent = self.on_click
        self.next = SlideView(self.doc, self.split)
        auto = os.path.splitext(path)[0] + '.notes.md'
        self.notes_path = notes or (auto if os.path.exists(auto) else None)
        if self.notes_path:
            self.keys = page_keys(path)
            self.notes = QTextBrowser(openExternalLinks=True)
            self.notes.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # keep keys for slide control
            self.notes.setStyleSheet('background:#1b1b1b; color:#eee; font-size:20px; border:none')
            self.watcher = QFileSystemWatcher([self.notes_path], self)
            self.watcher.fileChanged.connect(self.reload_notes)
            self.reload_notes()
        else:
            self.notes = SlideView(self.doc, self.split, half=1)
        self.clock = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.clock.setTextFormat(Qt.TextFormat.RichText)
        self.help = QLabel('→/Space next · ← prev · L pointer · B blackout · S timer · R reset · T set remaining · +/- ±1 min · V video · [ ] ∓5s · Z video full · 1/2/3 layout · F fullscreen · Q quit')
        self.help.setStyleSheet('color:#777; font-size:12px')

        self.body = QWidget()
        main = QVBoxLayout(self)
        main.addWidget(self.body, 1)
        main.addWidget(self.help)
        self.set_layout(layout)

        self.movies = find_movies(path, self.split)
        self.player, self.movie = QMediaPlayer(self), None   # movie: (rect, path) currently loaded
        self.player.setAudioOutput(QAudioOutput(self))
        self.player.setVideoSink(QVideoSink(self))
        self.player.videoSink().videoFrameChanged.connect(self.on_frame)

        # video controls (shown only on pages with a \\movie); NoFocus keeps arrow keys for slides
        self.vbar = QWidget()
        hb = QHBoxLayout(self.vbar)
        hb.setContentsMargins(0, 0, 0, 0)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.vtime = QLabel('0:00 / 0:00')
        self.btn_play = QPushButton('▶')
        btns = [(self.btn_play, self.play_pause), (QPushButton('« 5s'), lambda: self.skip(-5000)),
                (QPushButton('5s »'), lambda: self.skip(5000)), (QPushButton('⛶ Full'), self.toggle_full)]
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
            lambda st: self.btn_play.setText('❚❚' if st == QMediaPlayer.PlaybackState.PlayingState else '▶'))
        self.layout().insertWidget(1, self.vbar)

        self.aud = Audience(self)
        screens = QGuiApplication.screens()
        if len(screens) > 1:
            self.aud.setGeometry(screens[1].geometry())
            self.aud.showFullScreen()
        else:
            self.aud.resize(1280, 720)
            self.aud.show()
        self.resize(1400, 850)
        self.show()

        t = QTimer(self, interval=250)
        t.timeout.connect(self.tick)
        t.start()
        self.go(0)

    # --- navigation ---
    def go(self, n):
        n = max(0, min(self.doc.pageCount() - 1, n))
        if n != self.n:
            self.stop_video()
            if self.movies.get(n):                  # preload so the seek bar knows the duration
                self.load_video(self.movies[n][0])
        self.n = n
        if n and self.since is None and self.acc == 0:
            self.since = time.monotonic()           # first move starts the clock
        self.cur.page = self.aud.page = self.n
        if self.notes_path:
            self.show_notes()
        else:
            self.notes.page = self.n
        self.vbar.setVisible(bool(self.movies.get(self.n)))
        self.next.page = self.n + 1
        for v in (self.cur, self.next, self.notes, self.aud):
            v.update()
        self.tick()

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
        self.notes.setMarkdown(notes_for(self.md, (frame, ov)))

    # --- presenter layout ---
    def set_layout(self, n):
        """1: current | next over notes.  2: current | next, big notes below.  3: current | next, no notes."""
        old, self.body = self.body, QWidget()   # widgets move into the new container when added
        if n == 1:
            left, right = QVBoxLayout(), QVBoxLayout()
            left.addWidget(self.cur, 1)
            left.addWidget(self.clock)
            right.addWidget(self.next, 2)
            right.addWidget(self.notes, 5)
            g = QHBoxLayout(self.body)
            g.addLayout(left, 11)
            g.addLayout(right, 9)
        else:
            top = QHBoxLayout()
            top.addWidget(self.cur)
            top.addWidget(self.next)
            g = QVBoxLayout(self.body)
            g.addLayout(top, 4 if n == 2 else 1)
            g.addWidget(self.notes, 5)
            g.addWidget(self.clock)
        g.setContentsMargins(0, 0, 0, 0)
        self.notes.setVisible(n != 3)
        self.layout().replaceWidget(old, self.body)
        old.deleteLater()
        self.layout_no = n

    # --- video ---
    # Loaded-but-stopped shows the PDF poster; frames are drawn once playing or paused.
    def load_video(self, movie):
        self.movie = movie
        self.player.setSource(QUrl.fromLocalFile(movie[1]))

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

    def on_click(self, e):
        r = self.cur.target()
        if r is None:
            return
        if self.cur.full:
            self.play_pause()
            return
        pt = QPointF((e.position().x() - r.x()) / r.width(), (e.position().y() - r.y()) / r.height())
        for m in self.movies.get(self.n, []):
            if m[0].contains(pt):
                self.toggle_video(m)
                return

    # --- pointer ---
    def on_move(self, e):
        r = self.cur.target()
        if r is None:
            return
        rx, ry = (e.position().x() - r.x()) / r.width(), (e.position().y() - r.y()) / r.height()
        self.set_pointer((rx, ry) if 0 <= rx <= 1 and 0 <= ry <= 1 else None)

    def set_pointer(self, pt):
        self.aud.pointer, self.aud.mode = pt, self.mode
        self.aud.update()

    # --- timer ---
    def elapsed(self):
        return self.acc + (time.monotonic() - self.since if self.since is not None else 0)

    def tick(self):
        e = self.elapsed()
        r = self.dur - e
        cell = '<td style="padding:0 24px"><span style="color:#888;font-size:12px">{}</span><br>' \
               '<span style="font-size:40px;font-weight:600;color:{}">{}</span></td>'
        pause = ' ⏸' if self.since is None and e else ''
        self.clock.setText('<table><tr>'
                           + cell.format('slide', '#eee', f'{self.n + 1} / {self.doc.pageCount()}')
                           + cell.format('elapsed', '#eee', fmt(e) + pause)
                           + cell.format('remaining', '#f55' if r < 0 else '#eee', fmt(r))
                           + cell.format('pointer', '#eee', self.mode)
                           + (cell.format('audience', '#f55', 'BLACK') if self.aud.black else '')
                           + '</tr></table>')

    # --- keys (shared by both windows) ---
    def keyPressEvent(self, e):
        self.key(e, self)

    def key(self, e, win):
        k, K = e.key(), Qt.Key
        if k in (K.Key_Right, K.Key_Down, K.Key_PageDown, K.Key_Space, K.Key_Return, K.Key_J):
            self.go(self.n + 1)
        elif k in (K.Key_Left, K.Key_Up, K.Key_PageUp, K.Key_Backspace, K.Key_K):
            self.go(self.n - 1)
        elif k == K.Key_Home:
            self.go(0)
        elif k == K.Key_End:
            self.go(self.doc.pageCount() - 1)
        elif k == K.Key_L:
            self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
            self.set_pointer(self.aud.pointer)
            self.tick()
        elif k in (K.Key_B, K.Key_Period):
            self.aud.black = not self.aud.black
            self.aud.update()
            self.tick()
        elif k == K.Key_S:
            if self.since is None:
                self.since = time.monotonic()
            else:
                self.acc += time.monotonic() - self.since
                self.since = None
        elif k == K.Key_R:
            self.since, self.acc = None, 0.0
        elif k in (K.Key_Plus, K.Key_Equal):
            self.dur += 60
        elif k in (K.Key_Minus, K.Key_Underscore):
            self.dur -= 60
        elif k == K.Key_T:
            text, ok = QInputDialog.getText(self, 'Remaining time', 'Remaining (min, m:ss or h:mm:ss):',
                                            text=fmt(self.dur - self.elapsed()))
            try:
                if ok:
                    self.dur = self.elapsed() + parse_time(text)
            except ValueError:
                pass
        elif k == K.Key_V:
            self.play_pause()
        elif k in (K.Key_BracketLeft, K.Key_BracketRight):
            self.skip(-5000 if k == K.Key_BracketLeft else 5000)
        elif k == K.Key_Z:
            self.toggle_full()
        elif k in (K.Key_1, K.Key_2, K.Key_3):
            self.set_layout(k - K.Key_0)
        elif k == K.Key_F:
            win.showNormal() if win.isFullScreen() else win.showFullScreen()
        elif k == K.Key_Escape and win.isFullScreen():
            win.showNormal()
        elif k == K.Key_Q:
            QApplication.quit()

    def closeEvent(self, _):
        QApplication.quit()


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
        text = c.selectedText().replace(' ', '\n')      # Qt's paragraph separator
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
                QApplication.clipboard().setText(self.textCursor().selectedText().replace(' ', '\n'))
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
        self.info = QLabel()
        self.preview = QTextBrowser()
        self.preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview.setStyleSheet('background:#1b1b1b; color:#eee; font-size:16px; border:none')
        self.edit = EmacsEdit({'save': self.save, 'quit': self.close, 'search': self.search,
                               'next': lambda: self.show_page(self.page + 1, True),
                               'prev': lambda: self.show_page(self.page - 1, True),
                               'note': self.add_note, 'message': self.message})
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(12)
        self.edit.setFont(font)
        self.mini = QLineEdit(readOnly=True)                  # echo area / I-search prompt
        self.mini.installEventFilter(self)
        self.mini.textEdited.connect(self.search_update)
        if os.path.exists(self.path):
            with open(self.path, encoding='utf-8') as f:
                self.edit.setPlainText(f.read())

        left, right = QWidget(), QWidget()
        lv, rv = QVBoxLayout(left), QVBoxLayout(right)
        lv.addWidget(self.view, 3)
        lv.addWidget(self.info)
        lv.addWidget(self.preview, 2)
        rv.addWidget(self.edit, 1)
        rv.addWidget(self.mini)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([700, 800])
        QVBoxLayout(self).addWidget(split)
        self.setStyleSheet('QWidget{background:#111;color:#eee} QPlainTextEdit,QLineEdit{background:#1b1b1b}')

        self.edit.cursorPositionChanged.connect(self.on_cursor)
        self.edit.textChanged.connect(self.refresh)
        self.edit.document().modificationChanged.connect(self.set_title)
        self.edit.document().setModified(False)
        self.set_title(False)
        self.show_page(0, False)
        self.on_cursor()
        self.message('C-x C-s save · M-n/M-p page · C-c C-j notes for this page · C-s search · C-x C-c quit')
        self.resize(1500, 900)
        self.show()
        self.edit.setFocus()

    def message(self, text):
        if not self.searching:
            self.mini.setText(text)

    def set_title(self, modified):
        self.setWindowTitle(('*' if modified else '') + os.path.basename(self.path) + ' — Beamer Notes Editor')

    # --- notes <-> pages ---
    def key(self):
        return self.keys[self.page] if self.page < len(self.keys) else (str(self.page + 1), 1)

    def refresh(self):
        self.preview.setMarkdown(notes_for(parse_notes(self.edit.toPlainText()), self.key()))

    def section_at_cursor(self):
        """(frame, first click or None) of the heading above the cursor."""
        b = self.edit.textCursor().block()
        while b.isValid():              # ponytail: ignores ``` fences, unlike parse_notes
            m = HEAD_RE.match(b.text())
            if m:
                return m[1], int(m[2]) if m[2] else None
            b = b.previous()
        return None

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
        b = self.edit.document().firstBlock()
        while b.isValid():
            m = HEAD_RE.match(b.text())
            if m and m[1] == frame:
                lo = int(m[2]) if m[2] else None
                hi = int(m[3]) if m[3] else lo
                if lo is None:
                    wide = wide or b
                elif lo <= ov <= hi:
                    exact = exact or b
                anyb = anyb or b
            b = b.next()
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
        self.info.setText(f'page {i + 1} / {self.doc.pageCount()}    frame {frame}    click {ov}')
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
        b = self.edit.document().firstBlock()
        while b.isValid():
            m = HEAD_RE.match(b.text())
            if m and rank(m[1], int(m[2]) if m[2] else None) > new:
                break
            b = b.next()
        c = QTextCursor(self.edit.document())
        if b.isValid():
            c.setPosition(b.position())
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
        self.mini.setStyleSheet('' if not text or not found.isNull() else 'color:#f66')
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
    app.setApplicationName('Beamer Presenter Lite')
    app.setDesktopFileName('beamer-presenter-lite')
    path = a.pdf or QFileDialog.getOpenFileName(None, 'Open PDF', '', 'PDF (*.pdf)')[0]
    if not path:
        sys.exit(0)
    w = NotesEditor(path, a.notes) if a.edit else Presenter(path, a.duration, a.layout, a.notes)  # noqa: F841
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
