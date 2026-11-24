"""Phone rehearsal page for a beamer talk: each slide page, its speaker note, and read-aloud.

    bpl-rehearse talk.pdf [-n talk.notes.md] [-o talk-rehearse] [--lang en-US]

Writes OUT/index.html and OUT/img/*.jpg. Open index.html in a browser, or host the folder
(any static host, or a private claude.ai Artifact). Notes use the presenter's format and its
page-to-note mapping, so the page shows what the presenter shows. Needs pandoc for Markdown.
Parentheses in notes, (...) or full-width, are cues: shown dimmed, not read aloud.
"""
import argparse, html, json, os, shutil, subprocess, sys

from PyQt6.QtCore import QSize

import beamer_presenter_lite as bpl


def md_to_html(md):
    if not md.strip():
        return ''
    return subprocess.run(['pandoc', '-f', 'markdown', '-t', 'html'], input=md, capture_output=True,
                          text=True, check=True).stdout


def build(pdf, notes, out, lang='en-US', width=1280, title=None, quality=78):
    if not shutil.which('pandoc'):
        raise SystemExit('bpl-rehearse: pandoc not found (needed to turn the Markdown notes into HTML)')
    img_dir = os.path.join(out, 'img')
    os.makedirs(img_dir, exist_ok=True)
    for f in os.listdir(img_dir):
        if f.endswith('.jpg'):
            os.remove(os.path.join(img_dir, f))
    doc = bpl.Pdf(pdf)
    keys = bpl.page_keys(pdf)
    secs = bpl.load_notes(notes) if notes and os.path.exists(notes) else []
    pages = []
    for i, key in enumerate(keys):
        w, h = doc.pagePointSize(i).width(), doc.pagePointSize(i).height()
        name = f'img/p-{i + 1:03d}.jpg'
        if not doc.render(i, QSize(width, round(width * h / w))).save(os.path.join(out, name), 'JPG', quality):
            raise SystemExit(f'bpl-rehearse: could not write {name}')
        pages.append({'img': name, 'frame': key[0], 'ov': key[1], 'note': md_to_html(bpl.notes_for(secs, key))})
    page = (TEMPLATE.replace('__TITLE__', html.escape(title or os.path.splitext(os.path.basename(pdf))[0]))
            .replace('__LANG__', lang.replace("'", ''))
            .replace('/*PAGES*/[]', json.dumps(pages, ensure_ascii=False).replace('</', '<\\/')))
    with open(os.path.join(out, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(page)
    return len(pages)


def main():
    ap = argparse.ArgumentParser(prog='bpl-rehearse', description='Phone rehearsal page: slides, notes, read-aloud.')
    ap.add_argument('pdf')
    ap.add_argument('-n', '--notes', help='Markdown speaker notes (default: <pdf name>.notes.md)')
    ap.add_argument('-o', '--out', help='output folder (default: <pdf name>-rehearse)')
    ap.add_argument('--lang', default='en-US', help='read-aloud language, e.g. en-US, ja-JP (default en-US)')
    ap.add_argument('--width', type=int, default=1280, help='slide image width in pixels (default 1280)')
    ap.add_argument('--title', help='page title (default: PDF file name)')
    a = ap.parse_args()
    stem = os.path.splitext(a.pdf)[0]
    out = a.out or stem + '-rehearse'
    n = build(a.pdf, a.notes or stem + '.notes.md', out, a.lang, a.width, a.title)
    print(f'{out}/index.html: {n} pages', file=sys.stderr)


TEMPLATE = r'''<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=JetBrains+Mono:wght@400&display=swap">
<style>
/* Layout: slide on top, note below, one control bar fixed at the bottom (thumb reach). */
:root {
  --bg: #f3f4f8; --surface: #ffffff; --fg: #1b1d2a; --muted: #5d6178;
  --accent: #33339e; --cue: #8a5a00; --line: #d9dbe6;
  --body: "Inter", system-ui, -apple-system, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #12131a; --surface: #1c1e29; --fg: #e8e9f2; --muted: #9a9db3;
  --accent: #9ea3ff; --cue: #e0b25c; --line: #2e3142; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #12131a; --surface: #1c1e29; --fg: #e8e9f2; --muted: #9a9db3;
  --accent: #9ea3ff; --cue: #e0b25c; --line: #2e3142; color-scheme: dark }
html, body { height: 100%; }
body { background: var(--bg); color: var(--fg); font-family: var(--body); font-size: 17px; line-height: 1.5; }
main { max-width: 760px; margin: 0 auto;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 12px calc(150px + env(safe-area-inset-bottom, 0px)); display: grid; gap: 12px; }
.where { font-size: 13px; color: var(--muted); letter-spacing: .04em; font-variant-numeric: tabular-nums;
  display: flex; justify-content: space-between; gap: 8px; }
.slide { width: 100%; max-width: 100%; aspect-ratio: 16 / 9; object-fit: contain; background: #fff;
  border: 1px solid var(--line); border-radius: 6px; }
.note { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 4px 16px 12px; min-width: 0; }
.note h3 { font-size: 13px; font-weight: 600; color: var(--muted); margin: 10px 0 4px; text-wrap: balance; }
.note ul, .note ol { padding-left: 1.2em; margin: 6px 0; }
.note li { margin: 6px 0; }
.note p { margin: 4px 0; }
.note code { font-family: var(--mono); font-size: .86em; overflow-wrap: anywhere; }
.note .cue { color: var(--cue); font-size: .9em; }
.note.hidden > * { visibility: hidden; }
.note.hidden { position: relative; min-height: 120px; }
.note.hidden::after { content: "Tap to show the note"; position: absolute; inset: 0; display: grid; place-items: center;
  color: var(--muted); font-size: 15px; }
.note .speaking { background: color-mix(in srgb, var(--accent) 18%, transparent); border-radius: 4px; }
.tts { font-size: 13px; color: var(--cue); min-height: 0; }
.tts:empty { display: none; }
.empty { color: var(--muted); font-style: italic; padding: 8px 0; }
.bar { position: fixed; left: 0; right: 0; bottom: 0; background: var(--surface); border-top: 1px solid var(--line);
  padding: 8px max(12px, env(safe-area-inset-right, 0px)) calc(8px + env(safe-area-inset-bottom, 0px)) max(12px, env(safe-area-inset-left, 0px));
  display: grid; gap: 8px; }
.row { display: flex; gap: 8px; align-items: center; justify-content: center; flex-wrap: wrap; }
button, select { font: inherit; font-size: 15px; color: var(--fg); background: var(--bg); border: 1px solid var(--line);
  border-radius: 8px; padding: 10px 14px; min-height: 44px; }
button.main { background: var(--accent); color: var(--surface); border-color: var(--accent); font-weight: 600; min-width: 110px; }
button[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); font-weight: 600; }
button:focus-visible, select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
input[type=range] { width: 100%; accent-color: var(--accent); }
label { font-size: 13px; color: var(--muted); display: flex; gap: 6px; align-items: center; }
</style>

<main>
  <div class="where"><span id="where"></span><span id="count"></span></div>
  <div id="tts" class="tts" role="status"></div>
  <img id="slide" class="slide" alt="">
  <section id="note" class="note" aria-live="polite"></section>
</main>

<div class="bar">
  <input id="seek" type="range" min="1" value="1" aria-label="Page">
  <div class="row">
    <button id="prev" aria-label="Previous page">◀</button>
    <button id="speak" class="main">Read aloud</button>
    <button id="next" aria-label="Next page">▶</button>
  </div>
  <div class="row">
    <button id="auto" aria-pressed="false">Continuous</button>
    <button id="hide" aria-pressed="false">Hide note</button>
    <label for="rate">Speed
      <select id="rate"><option>0.8</option><option>0.9</option><option selected>1.0</option><option>1.1</option><option>1.2</option></select>
    </label>
  </div>
</div>

<script>
const PAGES = /*PAGES*/[];
const LANG = '__LANG__';
const $ = id => document.getElementById(id);
const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } },
                set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
const frames = {};
PAGES.forEach(p => frames[p.frame] = Math.max(frames[p.frame] || 0, p.ov));
const mainCount = Object.keys(frames).filter(f => !f.startsWith('B')).length;

let i = 0, speaking = false, auto = false, hidden = store.get('hide') === '1';
const synth = window.speechSynthesis;

// Parentheses in the notes are cues, not spoken: mark them so they can be shown dimmed and skipped.
function markCues(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const texts = []; while (walker.nextNode()) texts.push(walker.currentNode);
  for (const t of texts) {
    if (!/[(（]/.test(t.data) || t.parentElement.closest('code')) continue;
    const frag = document.createDocumentFragment();
    let last = 0;
    t.data.replace(/\([^()]*\)|（[^（）]*）/g, (m, at) => {
      frag.append(t.data.slice(last, at));
      const s = document.createElement('span'); s.className = 'cue'; s.textContent = m; frag.append(s);
      last = at + m.length;
    });
    frag.append(t.data.slice(last));
    t.replaceWith(frag);
  }
}

function spokenParts() {
  // One utterance per list item or paragraph, so the current one can be highlighted.
  const blocks = [...$('note').querySelectorAll('li, p')].filter(el => !el.querySelector('li, p'));
  return blocks.map(el => {
    const c = el.cloneNode(true);
    c.querySelectorAll('.cue').forEach(x => x.remove());
    const text = c.textContent.replace(/→/g, '').replace(/\s+/g, ' ').trim();
    return { el, text };
  }).filter(b => /[\p{L}\p{N}]/u.test(b.text));
}

function show(n) {
  stop();
  i = Math.max(0, Math.min(PAGES.length - 1, n));
  const p = PAGES[i];
  $('slide').src = p.img;
  $('slide').alt = `Slide ${p.frame}, step ${p.ov}`;
  const total = p.frame.startsWith('B') ? 'backup' : `of ${mainCount}`;
  $('where').textContent = `Slide ${p.frame} ${total}` + (frames[p.frame] > 1 ? ` · click ${p.ov}/${frames[p.frame]}` : '');
  $('count').textContent = `${i + 1} / ${PAGES.length}`;
  $('note').innerHTML = p.note || '<p class="empty">No note for this page.</p>';
  markCues($('note'));
  $('note').classList.toggle('hidden', hidden);
  $('seek').value = i + 1;
  store.set('page', String(i));
  if (location.hash !== `#p${i + 1}`) history.replaceState(null, '', `#p${i + 1}`);
  if (i + 1 < PAGES.length) new Image().src = PAGES[i + 1].img;
}

function stop() {
  speaking = false;
  if (synth) synth.cancel();
  document.querySelectorAll('.speaking').forEach(e => e.classList.remove('speaking'));
  $('speak').textContent = 'Read aloud';
}

let utterance = null, watchdog = 0;
const say = msg => { $('tts').textContent = msg; };

function speak() {
  if (!synth || !window.SpeechSynthesisUtterance) { say('This browser has no speech synthesis. Open the page in Safari or Chrome.'); return; }
  const parts = spokenParts();
  speaking = true; $('speak').textContent = 'Stop';
  const norm = s => s.replace('_', '-').toLowerCase();
  const voices = synth.getVoices();
  const voice = voices.find(v => norm(v.lang) === norm(LANG)) || voices.find(v => norm(v.lang).startsWith(norm(LANG).split('-')[0]));
  let k = 0;
  const step = () => {
    document.querySelectorAll('.speaking').forEach(e => e.classList.remove('speaking'));
    if (!speaking) return;
    if (k >= parts.length) {
      stop();
      if (auto && i + 1 < PAGES.length) { show(i + 1); setTimeout(speak, 600); }
      return;
    }
    const { el, text } = parts[k++];
    el.classList.add('speaking');
    el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    const u = new SpeechSynthesisUtterance(text);
    u.lang = LANG; if (voice) u.voice = voice;
    u.rate = parseFloat($('rate').value);
    u.onstart = () => { started = true; say(''); };
    u.onend = step;
    u.onerror = e => {
      say(`Speech error: ${e.error || 'unknown'}.` + (e.error === 'not-allowed' ? ' Tap Read aloud again.' : ''));
      if (e.error === 'not-allowed' || e.error === 'synthesis-unavailable') stop(); else if (speaking) step();
    };
    utterance = u;            // keep a reference: some browsers drop events of collected utterances
    synth.resume();           // Safari can be stuck in a paused state
    synth.speak(u);
  };
  let started = false;
  step();
  clearTimeout(watchdog);
  watchdog = setTimeout(() => {
    if (speaking && !started) say(`No sound after 3 s (voices: ${synth.getVoices().length}). ` +
      'On iPhone: turn the silent switch off and raise the volume, or open this page in Safari.');
  }, 3000);
}

$('prev').onclick = () => show(i - 1);
$('next').onclick = () => show(i + 1);
$('speak').onclick = () => speaking ? stop() : speak();
$('auto').onclick = () => { auto = !auto; $('auto').setAttribute('aria-pressed', auto); };
$('hide').onclick = () => {
  hidden = !hidden; store.set('hide', hidden ? '1' : '0');
  $('hide').setAttribute('aria-pressed', hidden); $('note').classList.toggle('hidden', hidden);
};
$('hide').setAttribute('aria-pressed', hidden);
$('note').onclick = () => { if ($('note').classList.contains('hidden')) $('note').classList.remove('hidden'); };
$('rate').value = store.get('rate') || '1.0';
$('rate').onchange = () => store.set('rate', $('rate').value);
$('seek').max = PAGES.length;
$('seek').oninput = () => show(parseInt($('seek').value, 10) - 1);
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowRight' || e.key === 'PageDown') show(i + 1);
  if (e.key === 'ArrowLeft' || e.key === 'PageUp') show(i - 1);
});
let x0 = null;
$('slide').addEventListener('touchstart', e => x0 = e.touches[0].clientX, { passive: true });
$('slide').addEventListener('touchend', e => {
  if (x0 === null) return;
  const dx = e.changedTouches[0].clientX - x0; x0 = null;
  if (Math.abs(dx) > 40) show(i + (dx < 0 ? 1 : -1));
});
if (synth) synth.getVoices();
const fromHash = /^#p(\d+)$/.exec(location.hash);
show(fromHash ? parseInt(fromHash[1], 10) - 1 : parseInt(store.get('page') || '0', 10) || 0);
window.addEventListener('hashchange', () => { const m = /^#p(\d+)$/.exec(location.hash); if (m && +m[1] - 1 !== i) show(+m[1] - 1); });
</script>
'''


if __name__ == '__main__':
    main()
