"""Markdown essenziale -> pagina HTML (Guida e Metodo, in locale e sul sito)."""
from __future__ import annotations

def frammento_markdown(md: str, link_schede: str = "") -> str:
    """Markdown -> HTML del solo contenuto (per le schede Istruzioni e Metodo del simulatore).
    I link interni /guida e /metodo diventano link alle schede (#istruzioni, #metodo),
    preceduti da `link_schede` (es. "../../gemello/ui/" quando il frammento sta in un'altra pagina)."""
    return _converti(md, link_schede)


def pagina_markdown(md: str, titolo: str, radice: str = "../../", attivo: str | None = None) -> str:
    """Pagina completa con testata, menu e pie' di pagina del sito (usata per i report)."""
    out = [_converti(md, radice + "gemello/ui/")]
    return _pagina(out, titolo, radice, attivo)


def _converti(md: str, link_schede: str) -> str:
    """Markdown essenziale -> HTML (titoli, paragrafi, elenchi, tabelle, grassetto, codice, link)."""
    import html as H
    import re

    def inline(t):
        t = H.escape(t)
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\w)", r"<i>\1</i>", t)
        t = re.sub(r"\[([^\]]+)\]\(/guida\)", lambda m: f'<a href="{link_schede}#istruzioni" data-goto="istruzioni">{m.group(1)}</a>', t)
        t = re.sub(r"\[([^\]]+)\]\(/metodo\)", lambda m: f'<a href="{link_schede}#metodo" data-goto="metodo">{m.group(1)}</a>', t)
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
    return "".join(out)


def _pagina(out, titolo, radice, attivo):
    r = radice
    cur = lambda k: ' aria-current="page"' if k == attivo else ""  # noqa: E731
    return f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><title>{titolo}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="{r}favicon.svg">
<link rel="stylesheet" href="{r}assets/sito.css"></head>
<body class="doc"><div class="wrap">
<div class="sito-testata"><a class="brand" href="{r}">
<svg class="brandmark" viewBox="0 0 64 64" role="img" aria-label="PS Prato Live"><rect x="2" y="2" width="60" height="60" rx="14" fill="#e11d2a"/><rect x="26.5" y="12" width="11" height="40" rx="3.5" fill="#fff"/><rect x="12" y="26.5" width="40" height="11" rx="3.5" fill="#fff"/></svg>
<div><div class="brandname">PS Prato <span class="live">Live</span></div><div class="brandtag">Simulatore del Pronto Soccorso · gemello digitale</div></div></a></div>
<nav class="sito-nav" aria-label="Sezioni del sito">
<a href="{r}">Dashboard</a>
<a class="evid" href="{r}gemello/ui/"{cur("simulatore")}>🔬 Simulatore</a>
<a href="https://github.com/iltempe/ps-prato/tree/main/data/ufficiali" target="_blank" rel="noopener">Dati ufficiali ASL</a>
</nav>
<div class="doc-contenuto">{"".join(out)}</div>
<p class="credits"><a href="https://github.com/iltempe" target="_blank" rel="noopener">Matteo Tempestini · @iltempe</a>
<a href="https://github.com/iltempe/ps-prato/tree/main/gemello" target="_blank" rel="noopener">Codice del modello</a>
<a href="{r}privacy.html">Privacy</a></p>
</div></body></html>"""
