"""Leitura dos sites de leiloeiros que rodam na plataforma Suporte Leilões.

Todos esses sites têm as mesmas rotas públicas:
  /leiloes                 lista dos leilões em andamento
  /leiloes/{id}            página do leilão (edital, visitação, retirada)
  /print/leiloes/{id}      versão para imprimir, com todos os lotes, lances e valor atual
"""
import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from .tempo import FUSO


def _txt(el):
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def _texto_limpo(html):
    s = BeautifulSoup(html, "html.parser")
    for x in s(["script", "style", "noscript", "svg"]):
        x.decompose()
    return s, " ".join(s.get_text(" ", strip=True).split())


def descobrir_ids(cliente, dominio):
    r = cliente.get(f"https://{dominio}/leiloes")
    r.raise_for_status()
    ids = re.findall(r"""href=["']?(?:https?://[^/"'\s>]+)?/leiloes/(\d+)(?=["'\s>?#])""", r.text)
    return sorted(set(int(x) for x in ids))


# ---------- página de impressão ----------
RE_DATA = re.compile(r"(\d{2}/\d{2}/\d{4})(?:\s*(?:-|às|a partir das|,)?\s*(\d{1,2})[h:](\d{2}))?")


def _dt(data, hh=None, mm=None):
    d = datetime.strptime(data, "%d/%m/%Y")
    if hh is None:
        return d.replace(hour=23, minute=59, tzinfo=FUSO), False
    return d.replace(hour=int(hh), minute=int(mm or 0), tzinfo=FUSO), True


def ler_impressao(cliente, dominio, leilao_id):
    url = f"https://{dominio}/print/leiloes/{leilao_id}"
    r = cliente.get(url)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    if "leiloes-print-page" not in r.text:
        raise RuntimeError(f"página de impressão em formato inesperado: {url}")
    dados = parse_impressao(r.text)
    dados["buscado_em"] = datetime.now(FUSO)
    return dados


def parse_impressao(html):
    s = BeautifulSoup(html, "html.parser")
    info = s.select_one(".leilao-info")
    titulo = _txt(info.select_one(".titulo")) if info else ""
    if not titulo:
        titulo = _txt(s.select_one(".page-header h2")).replace("Leilão:", "").strip()
    pracas = []
    modalidade = ""
    if info:
        for blk in info.select(".datas:not(.extra) > div"):
            nome = _txt(blk.find("strong"))
            fim = None
            for p in blk.find_all("p"):
                t = _txt(p)
                m = re.match(r"(Encerramento|Data)\s*:\s*" + RE_DATA.pattern, t)
                if m:
                    fim = (m.group(2), m.group(3), m.group(4))
            if fim:
                pracas.append({"nome": nome, "fim": fim})
        ex = info.select_one(".datas.extra")
        modalidade = _txt(ex).replace("Modalidade:", "").strip() if ex else ""
    lotes = []
    for tr in s.select(".leilao table tr"):
        num = tr.select_one(".lote-numero")
        if not num:
            continue
        img = tr.find("img")
        src = img.get("src", "") if img else ""
        bem = re.search(r"/bens/(\d+)/", src)
        loc = tr.select_one(".leilao-lote-titulo small")
        stats = {}
        for st in tr.select(".stats"):
            classes = [c for c in st.get("class", []) if c != "stats"]
            stats[classes[0] if classes else "x"] = _txt(st)
        lances = re.search(r"(\d+)", stats.get("lances", "0")) or None
        valor = re.search(r"R\$\s*([\d\.]+,\d{2})", stats.get("valorAtual", ""))
        lotes.append({
            "numero": _txt(num),
            "bem": bem.group(1) if bem else None,
            "titulo": _txt(tr.select_one(".leilao-lote-titulo .titulo")),
            "desc": _txt(tr.select_one(".leilao-lote-titulo .desc")),
            "local": _txt(loc).replace("Localização:", "").strip() if loc else "",
            "lances": int(lances.group(1)) if lances else 0,
            "valor": float(valor.group(1).replace(".", "").replace(",", ".")) if valor else None,
            "situacao": " ".join(tr.get("class", [])),
        })
    return {"titulo": titulo, "pracas": pracas, "modalidade": modalidade, "lotes": lotes}


# ---------- página do leilão ----------
def ler_pagina(cliente, dominio, leilao_id):
    url = f"https://{dominio}/leiloes/{leilao_id}"
    r = cliente.get(url)
    r.raise_for_status()
    return parse_pagina(r.text)


def _corta(t, n=220):
    t = t.strip(" .;:-")
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def parse_pagina(html):
    s, texto = _texto_limpo(html)
    docs = []
    for a in s.find_all("a", href=re.compile(r"\.pdf($|\?)", re.I)):
        rotulo = _txt(a) or "Documento"
        href = a["href"]
        if href not in [d["url"] for d in docs]:
            docs.append({"rotulo": rotulo[:60], "url": href})
    visita = re.search(r"Informação de visitação:\s*(.+?)(?=Informação de retirada:|$)", texto)
    retirada = re.search(r"Informação de retirada:\s*(.+?)(?=\s(?:Veículos|O VEÍCULO|Os veículos|OS VEÍCULOS|Cadastre-se|Edital)\b|$)", texto)
    if not visita:
        visita = re.search(r"((?:A |a )?visitação[^.]{10,260})", texto)
    datas = []
    for m in re.finditer(r"(?:1º|2º|3º|Primeiro|Segundo|Terceiro|[ÚU]nic[oa]|Data única|Encerramento)[^0-9]{0,30}" + RE_DATA.pattern, texto, re.I):
        datas.append((m.group(1), m.group(2), m.group(3)))
    tipo = re.search(r"Aplicar filtros (Judicial|Extrajudicial)\b", texto)
    i = texto.find("Modalidade:")
    trecho = texto[i: i + 1800] if i >= 0 else texto[:1800]
    return {
        "docs": docs,
        "natureza": tipo.group(1) if tipo else "",
        "trecho": trecho,
        "visita": _corta(visita.group(1)) if visita else "",
        "retirada": _corta(retirada.group(1)) if retirada else "",
        "datas": datas,
    }


def edital_de(docs):
    for d in docs:
        if "edital" in d["rotulo"].lower():
            return d["url"]
    return docs[0]["url"] if docs else ""


def montar_pracas(pracas_impressao, datas_pagina):
    """Junta as datas da impressão com as da página (que às vezes trazem o horário)."""
    horas = {}
    for d, hh, mm in datas_pagina:
        if hh is not None:
            horas.setdefault(d, (hh, mm))
    out = []
    fonte = pracas_impressao or [{"nome": "", "fim": x} for x in datas_pagina]
    vistos = set()
    for p in fonte:
        d, hh, mm = p["fim"]
        if hh is None and d in horas:
            hh, mm = horas[d]
        dt, com_hora = _dt(d, hh, mm)
        if dt in vistos:
            continue
        vistos.add(dt)
        out.append({"nome": p.get("nome") or "", "fim": dt, "com_hora": com_hora})
    out.sort(key=lambda x: x["fim"])
    return out


def praca_atual(pracas, agora):
    """A praça que ainda está aberta (ou a última, se todas já fecharam)."""
    abertas = [p for p in pracas if p["fim"] > agora - timedelta(hours=1)]
    return abertas[0] if abertas else (pracas[-1] if pracas else None)
