"""Turn Markdown speaker notes (FOO.notes.md) into beamer notes, for PDFs with note pages.

  python3 notes2tex.py main.notes.md main.notes.tex      (needs pandoc)

Then, in the preamble of a build that shows notes:
  \\setbeameroption{show notes on second screen=right}
  \\input{main.notes.tex}

Each slide gets the sections whose key matches its frame number (B-prefixed after
\\appendix) and overlay, like beamer-presenter-lite does. No \\note in the .tex needed.
"""
import re
import subprocess
import sys

PREAMBLE = r"""% Generated from SRC by notes2tex.py; edit the Markdown, not this file.
\makeatletter
\providecommand{\tightlist}{\setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
\DeclareUnicodeCharacter{2192}{\ensuremath{\to}}
\DeclareUnicodeCharacter{2190}{\ensuremath{\leftarrow}}
\DeclareUnicodeCharacter{2264}{\ensuremath{\le}}
\DeclareUnicodeCharacter{2265}{\ensuremath{\ge}}
\DeclareUnicodeCharacter{2260}{\ensuremath{\ne}}
\DeclareUnicodeCharacter{2248}{\ensuremath{\approx}}
\DeclareUnicodeCharacter{00D7}{\ensuremath{\times}}
% \bnote@def{KEY@OVERLAY}{text}: append text; overlay 0 = every overlay of the frame
\long\def\bnote@def#1#2{\@ifundefined{bnote@#1}{\@namedef{bnote@#1}{}}{}%
  \expandafter\g@addto@macro\csname bnote@#1\endcsname{#2\par}}
\def\bnote@add#1{\@ifundefined{bnote@#1}{}{%
  \expandafter\g@addto@macro\expandafter\beamer@notes\expandafter{\csname bnote@#1\endcsname}}}
% at the end of each slide, before beamer decides whether it has notes
\let\bnote@origend\beamer@framenotesend
\def\beamer@framenotesend{%
  \edef\bnote@key{\ifbeamer@inappendix B\fi\the\c@framenumber}%
  \bnote@add{\bnote@key @0}%
  \bnote@add{\bnote@key @\the\beamer@slideinframe}%
  \bnote@origend}
"""


def sections(path):
    """[(frame, lo, hi, title, markdown)], same format as beamer_presenter_lite.load_notes."""
    # ponytail: duplicated from beamer_presenter_lite.load_notes so this runs without PyQt6
    secs, cur, fence = [], None, False
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.lstrip().startswith(('```', '~~~')):
                fence = not fence
            m = not fence and re.match(r'#[ \t]+(B?\d+)(?:\.(\d+)(?:-(\d+))?)?(?=\s|$)(.*)', line)
            if m:
                frame, lo, hi, title = m.groups()
                lo = int(lo) if lo else None
                cur = [frame, lo, int(hi) if hi else lo, title.strip(), '']
                secs.append(cur)
            elif cur:
                cur[4] += line
    return secs


def md2tex(md):
    if not md.strip():
        return ''
    return subprocess.run(['pandoc', '-f', 'gfm', '-t', 'latex', '--wrap=preserve'], input=md,
                          capture_output=True, text=True, check=True).stdout.strip()


def main(src, dst):
    out = [PREAMBLE.replace('SRC', src)]
    for frame, lo, hi, title, md in sections(src):
        body = (r'\textbf{%s}\par' % md2tex(title) if title else '') + '\n' + md2tex(md)
        for ov in ([0] if lo is None else range(lo, hi + 1)):
            out.append(r'\bnote@def{%s@%d}{%%' % (frame, ov) + '\n' + body + '}\n')
    out.append('\\makeatother\n')
    with open(dst, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))


if __name__ == '__main__':
    main(*sys.argv[1:3])
