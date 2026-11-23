"""Convert beamer \\note{...} blocks of a .tex file into Markdown notes for beamer-presenter-lite.

  python3 tex2notes.py main.tex main.notes.md      (needs pandoc)
"""
import re, subprocess, sys
src = open(sys.argv[1], encoding='utf-8').read()
src = re.sub(r'(?<!\\)%.*', '', src)          # drop comments

def group(s, i):                               # s[i] == '{' -> (body, end index)
    depth = 0
    for j in range(i, len(s)):
        c = s[j]
        if c == '\\': continue
        if c == '{' and s[j-1] != '\\': depth += 1
        elif c == '}' and s[j-1] != '\\':
            depth -= 1
            if depth == 0: return s[i+1:j], j + 1
    raise ValueError('unbalanced')

def tex2md(t):
    t = t.replace(r'\setlength\itemsep{1pt}', '').replace(r'\par', '\n\n')
    t = re.sub(r'\\quad', ' · ', t)
    t = t.replace(r'$\to$', '→').replace(r'\(\to\)', '→').replace(r'$\times$', '×')
    t = re.sub(r'\\badge\{([^}]*)\}', r'(\1)', t)
    out = subprocess.run(['pandoc', '-f', 'latex', '-t', 'gfm', '--wrap=none'], input=t,
                         capture_output=True, text=True, check=True).stdout
    # inline math -> plain text (Qt's Markdown has no math)
    out = re.sub(r'\$`(.*?)`\$', lambda m: m.group(1).replace(r'\le', ' ≤ ').replace(r'\ge', ' ≥ ').replace('  ', ' ').strip(), out)
    return out.strip()

frame, backup, out = 0, False, ['<!-- Speaker notes for main.pdf. "# N" = frame N (footer number), "# N.k" = its k-th click,',
                                 '     "# N.a-b" = clicks a..b, "# BN" = backup N. Loaded by beamer-presenter-lite. -->', '']
pos = 0
for m in re.finditer(r'\\appendix\b|\\begin\{frame\}|\\note(<[^>]*>)?\s*\{', src):
    if m.group(0) == r'\appendix':
        backup, frame = True, 0
    elif m.group(0).startswith(r'\begin'):
        frame += 1
    else:
        body, _ = group(src, m.end() - 1)
        ov = (m.group(1) or '')[1:-1]
        key = ('B' if backup else '') + str(frame) + (f'.{ov}' if ov else '')
        title = ''
        tm = re.match(r'\s*\\textbf\{', body)
        if tm:
            title, end = group(body, tm.end() - 1)
            body = body[end:]
            title = re.sub(r'^\s*B?\d+\\?\.\s*', '', tex2md(title))
        out += [f'# {key} {title}'.rstrip(), '', tex2md(body), '']
open(sys.argv[2], 'w', encoding='utf-8').write('\n'.join(out).replace('\xa0', ' '))
