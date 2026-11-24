# Beamer Presenter Lite

Presenter for beamer PDFs: speaker notes, laser/pointer/pen annotations, slide overview, timer & pace bar, blackout/whiteout, `\movie` playback.

## Install

```sh
pipx install .                              # or: uv tool install .; command: bpresent
bpresent --install-desktop                  # optional, Linux app menu
```

## Use

```sh
bpresent main.pdf [-d MINUTES] [-l 1|2|3]   # present
bpresent --edit main.pdf                    # edit notes (Emacs keys + Markdown highlight)
```

Notes come from `main.notes.md` next to the PDF, or from the right half of a PDF
built with `show notes on second screen=right`.

```markdown
# 4       frame 4 (footer number), every click
# 4.2     frame 4, click 2
# 5.1-3   frame 5, clicks 1-3
# B1      first frame after \appendix
```

### Keys

- **Navigation**: `→`/`Space`/`Enter`/`J`/Wheel next, `←`/`Shift+Enter`/`Backspace`/`K` prev, `num`+`Enter` quick jump, `Home`/`End`, `G` slide overview grid, `:` or `Ctrl+G` jump dialog
- **Pointer & Pen**: `L` cycle mode (laser/pointer/pen/eraser/off), `D`/`E` toggle pen/eraser, right-drag in pen mode to erase, `P` pen color, `U`/`Ctrl+Z` undo, `C`/`Shift+C` clear page/all
- **Timer & Notes**: `S`/`R` start-pause/reset timer, `T`/`+`/`-` remaining time, `Ctrl++`/`Ctrl+-` notes font size
- **Display & Video**: `B`/`.` blackout, `W`/`,` whiteout, `X` swap screens, `V`/`[`/`]`/`Z` video, `Alt+1`/`2`/`3` layout (also via footer layout & swap buttons), `F` fullscreen, `?`/`H` shortcuts, `Q` quit

## Tools

- `notes2tex.py main.notes.md main.notes.tex`: notes for a beamer note-page build (pandoc)
- `tex2notes.py main.tex main.notes.md`: move existing `\note{}` to Markdown (pandoc)
- `beamer-notes.el`: Emacs; `beamer-notes-edit-with-pdf` (notes + PDF, `C-c C-x t` right/below),
  `beamer-notes-side-by-side` (notes + .tex), `beamer-notes-jump`

```elisp
(use-package beamer-notes
  :load-path "~/src/github.com/3tty0n/beamer-presenter-lite"
  :commands (beamer-notes-side-by-side beamer-notes-edit-with-pdf beamer-notes-jump)
  :bind (("C-c C-x n" . beamer-notes-side-by-side)
         ("C-c C-x p" . beamer-notes-edit-with-pdf)
         ("C-c C-x j" . beamer-notes-jump)))
```

## Phone rehearsal page (`bpl-rehearse`)

Turns the PDF and its Markdown notes into a static page for practising on a phone:
one page per slide overlay with its note, swipe or buttons to move, and read-aloud
with the browser's speech voices (Continuous reads on to the next page).

```console
bpl-rehearse talk.pdf                      # notes: talk.notes.md, output: talk-rehearse/
bpl-rehearse talk.pdf -o out --lang ja-JP  # Japanese voice
```

It writes `index.html` and `img/*.jpg`. Open `index.html` in a browser, or put the
folder on any static host. Notes use the same format and page mapping as the presenter.
Parentheses in a note, `(...)` or `（…）`, are cues: shown dimmed and not read aloud.
Needs pandoc.
