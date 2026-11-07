"""Markdown essenziale -> pagina HTML (Guida e Metodo, in locale e sul sito)."""
from __future__ import annotations

def pagina_markdown(md: str, titolo: str, css: str = "style.css", indietro: str = "./") -> str:
    """Markdown essenziale -> HTML (titoli, paragrafi, elenchi, tabelle, grassetto, codice, link)."""
    import html as H
    import re

    def inline(t):
        t = H.escape(t)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<i>\1</i>", t)
        t = re.sub(r"\[([^\]]+)\]\(/(guida|metodo)\)", r'<a href="\2.html">\1</a>', t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
        return t

    out, righe, i = [], md.splitlines(), 0
    while i < len(righe):
        r = righe[i]
        if r.strip().startswith("```"):
            j = i + 1
            while j < len(righe) and not righe[j].strip().startswith("```"):
                j += 1
            out.append("<pre>" + H.escape("\n".join(x.strip() for x in righe[i + 1:j])) + "</pre>")
            i = j + 1
            continue
        m = re.match(r"(#{1,4}) (.*)", r)
        if m:
            n = len(m.group(1))
            ident = re.sub(r"[^a-z0-9]+", "-", m.group(2).lower()).strip("-")
            out.append(f'<h{n} id="{ident}">{inline(m.group(2))}</h{n}>')
        elif r.startswith("|"):
            tab = []
            while i < len(righe) and righe[i].startswith("|"):
                tab.append([c.strip() for c in righe[i].strip("|").split("|")])
                i += 1
            corpo = [x for x in tab[1:] if not all(set(c) <= set("-: ") for c in x)]
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in tab[0]) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in x) + "</tr>" for x in corpo)
                       + "</tbody></table>")
            continue
        elif re.match(r"\s*([-*]|\d+\.) ", r):
            num = bool(re.match(r"\s*\d+\.", r))
            items = []
            while i < len(righe) and re.match(r"\s*([-*]|\d+\.) ", righe[i]):
                items.append(re.sub(r"\s*([-*]|\d+\.) ", "", righe[i], count=1))
                i += 1
                while i < len(righe) and righe[i].startswith("  ") and righe[i].strip() and not re.match(r"\s*([-*]|\d+\.) ", righe[i]):
                    items[-1] += " " + righe[i].strip()
                    i += 1
            tag = "ol" if num else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        elif r.startswith(">"):
            q = []
            while i < len(righe) and righe[i].startswith(">"):
                q.append(righe[i][1:].strip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(q))}</blockquote>")
            continue
        elif r.strip() == "---":
            out.append("<hr>")
        elif r.strip():
            par = [r]
            while i + 1 < len(righe) and righe[i + 1].strip() and not re.match(r"(#|\||```|\s*[-*] |\s*\d+\. |> )", righe[i + 1]):
                i += 1
                par.append(righe[i])
            out.append("<p>" + inline(" ".join(par)) + "</p>")
        i += 1
    return f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><title>{titolo}</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="{css}">
<style>body{{max-width:900px;margin:0 auto;padding:24px 28px 60px;background:var(--surface-1)}} h1{{font-size:24px}}
h2{{font-size:19px;margin-top:32px;border-bottom:1px solid var(--grid);padding-bottom:4px}} h3{{font-size:16px;margin-top:22px}}
p,li{{font-size:15px;line-height:1.6}} table{{margin:10px 0}} td,th{{text-align:left!important;vertical-align:top}}
pre{{background:var(--surface-0);padding:10px;border-radius:6px;overflow-x:auto}}
blockquote{{border-left:3px solid var(--accent);margin:12px 0;padding:4px 14px;color:var(--text-secondary)}}</style>
</head><body class="viz-root"><p><a href="{indietro}">← torna al simulatore</a></p>{"".join(out)}</body></html>"""

