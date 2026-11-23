# Beamer Presenter Lite

Presenter for beamer PDFs: speaker notes, laser pointer, timer, blackout, `\movie` playback.

## Install

```sh
pipx install .                              # or: uv tool install .
beamer-presenter-lite --install-desktop     # optional, Linux app menu
```

## Use

```sh
beamer-presenter-lite main.pdf [-d MINUTES] [-l 1|2|3]   # present
beamer-presenter-lite --edit main.pdf                    # edit notes (Emacs keys)
```

Notes come from `main.notes.md` next to the PDF, or from the right half of a PDF
built with `show notes on second screen=right`.

```markdown
# 4       frame 4 (footer number), every click
# 4.2     frame 4, click 2
# 5.1-3   frame 5, clicks 1-3
# B1      first frame after \appendix
```

Keys: → / ← pages, L pointer, B blackout, S / R timer, T / + / - remaining time,
V / [ / ] / Z video, 1 / 2 / 3 layout, F fullscreen, Q quit.

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
