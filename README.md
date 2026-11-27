# Beamer Presenter Lite

Offline presenter for Beamer PDFs with speaker notes, laser/pen annotations, region zoom, resizable layouts, timer, and `\movie` playback.

## Install

```sh
pipx install .              # or: uv tool install . (provides `bpresent` and `bpl-rehearse`)
bpresent --install-desktop  # optional: add Linux desktop menu entries & icons
```

## Usage

```sh
bpresent main.pdf [-d MINUTES] [-l 1|2|3]   # present (-d: talk duration, -l: layout)
bpresent --edit main.pdf                    # edit Markdown notes (Emacs keys)
bpresent --reset-layout                     # restore default pane layout & sizes
```

### Speaker Notes

Notes are loaded from `<pdf>.notes.md` (auto-reloaded on save), `--notes FILE`, or the right half of a PDF built with `\setbeameroption{show notes on second screen=right}`.

```markdown
# 4       frame 4 (footer number), all clicks
# 4.2     frame 4, click 2
# 5.1-3   frame 5, clicks 1–3
# B1      first backup frame after \appendix
```

### Shortcuts

Press `?` or `H` in the presenter window for the full cheat sheet.

| Category | Keys | Action |
| :--- | :--- | :--- |
| **Navigate** | `→` / `Space` / `Enter` / `J` / Wheel | Next slide |
| | `←` / `Shift+Enter` / `Backspace` / `K` | Previous slide |
| | `<num>` + `Enter` / `:` / `Ctrl+G` | Jump to frame or page (`p12`) |
| | `G` / `Home` / `End` | Slide overview / first / last |
| **Pointer & Pen** | `L` / `D` / `E` / `P` | Cycle mode / pen / eraser / color |
| | `Right-drag` (in pen) / `U` / `C` | Erase / undo / clear (`Shift+C`: all) |
| **Zoom** | `M` / `Ctrl+Drag` / `Ctrl+Wheel` | Zoom region (`Shift+M`: re-select, click: 2×) |
| | `Shift+Drag` / Middle-drag / `Esc` | Pan zoomed view / reset zoom (`Ctrl+0`) |
| **Timer & Notes** | `S` / `R` / `T` / `+` / `-` | Start-pause / reset / set / ±1 min |
| | `Ctrl++` / `Ctrl+-` | Notes font size |
| **Display & Video** | `B` (`.`) / `W` (`,`) / `X` / `F` / `Q` | Blackout / whiteout / swap screens / fullscreen / quit |
| | `Alt+1` / `2` / `3` | Switch layout (or use footer buttons) |
| | `V` / `[` / `]` / `Z` | Play-pause video / ∓5s / fullscreen video |

**Customizing panes:** Drag pane borders to resize (double-click to reset) and drag pane headers onto another pane to swap positions. Layouts persist across sessions.

## Companion Tools

- **Phone Rehearsal (`bpl-rehearse`)**: Exports a PDF and `.notes.md` into a static mobile-friendly page with swipe navigation and browser TTS (`(...)` / `（…）` cues are dimmed and skipped; requires `pandoc`).
  ```sh
  bpl-rehearse talk.pdf [-o out] [--lang ja-JP]
  ```
- **TeX Conversion**: `notes2tex.py main.notes.md main.notes.tex` and `tex2notes.py main.tex main.notes.md` (requires `pandoc`).
- **Emacs (`beamer-notes.el`)**:
  ```elisp
  (use-package beamer-notes
    :load-path "~/src/github.com/3tty0n/beamer-presenter-lite"
    :commands (beamer-notes-side-by-side beamer-notes-edit-with-pdf beamer-notes-jump)
    :bind (("C-c C-x n" . beamer-notes-side-by-side)
           ("C-c C-x p" . beamer-notes-edit-with-pdf)
           ("C-c C-x j" . beamer-notes-jump)))
  ```
