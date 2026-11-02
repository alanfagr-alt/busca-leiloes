"""Roda os coletores, junta tudo e grava os arquivos que a página lê.

Uso:  python -m robo.montar            (rodada completa)
      python -m robo.montar --sem-fipe (sem consultar a FIPE, para teste rápido)
"""
import argparse
import concurrent.futures as cf
import json
import re
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from . import suporte_leiloes as sl
from .fipe import Fipe
from .geo import Geo
from .http import Cliente
from .tempo import FUSO, agora
from .veiculos import interpretar, observacao

RAIZ = Path(__file__).resolve().parent.parent
REVER_SEM_VEICULO = timedelta(days=7)
REVER_PAGINA = timedelta(days=3)


def ler_json(caminho, padrao):
    try:
        return json.load(open(caminho))
    except (FileNotFoundError, json.JSONDecodeError):
        return padrao


def gravar_json(caminho, obj, compacto=False):
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w") as f:
        if compacto:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")


def desde(iso, momento):
    try:
        return momento - datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return timedelta(days=9999)


def data_provisoria(praca, buscado_em):
    """Sem data marcada, a impressão mostra o horário do servidor. Isso não é data de leilão."""
    dif = abs((praca["fim"] - buscado_em).total_seconds())
    if not praca["com_hora"] or dif > 6 * 3600:
        return False
    return min((praca["fim"].minute - buscado_em.minute) % 60, (buscado_em.minute - praca["fim"].minute) % 60) <= 2


SIGLAS = {"RPCDETRO", "DETRO", "SEOP", "DETRAN", "RJ", "SP", "MG", "GM", "VW", "BMW", "JAC", "SUV", "HSE", "MT", "LT", "LTZ",
          "GLS", "XEI", "XLI", "SEL", "HLX", "HPE", "ASX", "ABS", "CVT", "MPI", "LTDA", "PCERJ", "RPCDETROPCERJ"}


def titulo_bonito(t):
    from .veiculos import MARCAS
    t = re.sub(r"(?i)\(?\s*(imagem meramente ilustrativa|visita[çc][ãa]o)\s*\)?", "", t or "").strip(" -–|,")
    t = re.sub(r"\s{2,}", " ", t)
    letras = [c for c in t if c.isalpha()]
    if letras and sum(c.isupper() for c in letras) > 0.85 * len(letras):
        palavras = []
        for w in t.split(" "):
            partes = []
            for p in w.split("/"):
                nucleo = re.sub(r"[^\wÀ-ú-]", "", p).upper()
                if any(ch.isdigit() for ch in p) or nucleo in SIGLAS:
                    partes.append(p.upper())
                elif nucleo in MARCAS or nucleo in ("BENZ", "ROVER", "ENFIELD"):
                    partes.append(p.capitalize())
                else:
                    partes.append(p.lower())
            palavras.append("/".join(partes))
        t = " ".join(palavras)
        t = t[:1].upper() + t[1:]
    return t if len(t) <= 95 else t[:94].rsplit(" ", 1)[0] + "…"


def modo_bonito(m):
    m = (m or "").lower()
    if "presencial" in m and "online" in m:
        return "Online e presencial"
    if "presencial" in m:
        return "Presencial"
    return "Só online" if "online" in m else (m.capitalize() or "Online")


class Coleta:
    def __init__(self, fontes_cfg, estado, geo, momento):
        self.cfg = fontes_cfg
        self.estado = estado
        self.geo = geo
        self.momento = momento
        self.cliente = Cliente(intervalo=1.0)

    def fonte(self, fonte):
        dom = fonte["dominio"]
        res = {"dominio": dom, "nome": fonte["nome"], "ok": True, "erro": "", "avisos": [],
               "paginas_lidas": 0, "leiloes": []}
        try:
            ids = sl.descobrir_ids(self.cliente, dom)
        except Exception as e:
            res.update(ok=False, erro=f"não abriu a lista de leilões ({str(e)[:160]})")
            return res
        if not ids:
            res.update(ok=False, erro="a lista de leilões veio vazia")
            return res
        falhas = 0
        for lid in ids:
            try:
                item = self.leilao(fonte, lid, res)
            except Exception as e:
                falhas += 1
                res["avisos"].append(f"leilão {lid}: {str(e)[:200]}")
                continue
            if item:
                res["leiloes"].append(item)
        if res["paginas_lidas"] == 0 and falhas:
            res.update(ok=False, erro="nenhuma página de leilão pôde ser lida")
        elif falhas > max(3, res["paginas_lidas"] // 3):
            res.update(ok=False, erro=f"{falhas} leilões falharam na leitura")
        return res

    def leilao(self, fonte, lid, res):
        dom = fonte["dominio"]
        k = f"{dom}/{lid}"
        st = self.estado["leiloes"].get(k, {})
        if st.get("situacao") == "encerrado":
            return None
        if st.get("situacao") in ("sem_veiculos", "sem_data", "sem_impressao") and desde(st.get("checado"), self.momento) < REVER_SEM_VEICULO:
            return None
        try:
            imp = sl.ler_impressao(self.cliente, dom, lid)
        except RuntimeError as e:
            if "formato inesperado" not in str(e):
                raise
            imp = None
        if imp is None:
            # venda direta e alguns leilões especiais não têm a versão para imprimir: revê em 7 dias
            self.estado["leiloes"][k] = {"situacao": "sem_impressao", "checado": self.momento.isoformat()}
            res["avisos"].append(f"leilão {lid}: sem página de impressão (revejo em 7 dias)")
            return None
        res["paginas_lidas"] += 1
        veics = []
        for i, l in enumerate(imp["lotes"]):
            if l["valor"] is None or re.search(r"retirad|vendid|cancelad|arrematad", l["situacao"], re.I):
                continue
            v = interpretar(l["titulo"], l["desc"])
            if v:
                veics.append((i, l, v))
        if not veics:
            self.estado["leiloes"][k] = {"situacao": "sem_veiculos", "checado": self.momento.isoformat()}
            return None

        meta = st.get("meta")
        if not meta or desde(st.get("meta_em"), self.momento) >= REVER_PAGINA:
            try:
                pg = sl.ler_pagina(self.cliente, dom, lid)
                meta = {k2: pg[k2] for k2 in ("docs", "visita", "retirada", "datas", "natureza", "trecho")}
                st["meta"], st["meta_em"] = meta, self.momento.isoformat()
            except Exception as e:
                res["avisos"].append(f"leilão {lid}: página do leilão não abriu ({str(e)[:120]})")
                meta = meta or {"docs": [], "visita": "", "retirada": "", "datas": [], "natureza": "", "trecho": ""}

        pracas = sl.montar_pracas(imp["pracas"], [tuple(x) for x in meta["datas"]])
        pracas = [p for p in pracas if not data_provisoria(p, imp["buscado_em"])]
        if not pracas:
            self.estado["leiloes"][k] = {"situacao": "sem_data", "checado": self.momento.isoformat()}
            return None
        if pracas[-1]["fim"] < self.momento - timedelta(hours=2):
            self.estado["leiloes"][k] = {"situacao": "encerrado", "fim": pracas[-1]["fim"].isoformat()}
            return None
        atual = sl.praca_atual(pracas, self.momento)

        patio = self.geo.patio(dom, imp["titulo"], meta.get("trecho", ""))
        padrao = self.geo.de_localizacao(fonte.get("cidade_padrao", "Rio de Janeiro/RJ").replace("/", " / "))
        iniciais = st.get("iniciais", {})
        tag_praca = atual["fim"].date().isoformat()
        numeros = [l["numero"] for _, l, _ in veics]
        lotes = []
        for i, l, v in veics:
            num = l["numero"] or str(i + 1)
            chave = f"{num}.{i}" if numeros.count(l["numero"]) > 1 else num
            if l["lances"] == 0:
                iniciais[f"{tag_praca}|{chave}"] = l["valor"]
            if patio:
                local = {"nome": patio["nome"], "endereco": patio.get("endereco", ""), "rotulo": patio["rotulo"],
                         "lat": patio["lat"], "lon": patio["lon"], "aprox": bool(patio.get("aprox"))}
            else:
                mun = (self.geo.de_localizacao(l["local"]) or self.geo.no_texto(l["desc"])
                       or self.geo.no_texto(meta.get("trecho", "")))
                aprox = mun is None or bool(mun and mun.get("aprox_estado"))
                mun = mun or padrao
                local = {"nome": f"{mun['nome']} ({mun['uf']})", "endereco": "", "rotulo": mun["nome"],
                         "lat": mun["lat"], "lon": mun["lon"], "aprox": aprox, "uf": mun["uf"]}
            lotes.append({"numero": num, "chave": chave, "v": v, "obs": observacao(l["titulo"], l["desc"]),
                          "atual": l["valor"], "lances": l["lances"],
                          "inicial": iniciais.get(f"{tag_praca}|{chave}"), "local": local})
        st.update(situacao="veiculos", checado=self.momento.isoformat(), fim=pracas[-1]["fim"].isoformat(),
                  iniciais={a: b for a, b in iniciais.items() if a.split("|")[0] >= self.momento.date().isoformat()})
        self.estado["leiloes"][k] = st

        orgao = fonte.get("orgao", "")
        for chave_t, nome_org in (fonte.get("orgao_por_titulo") or {}).items():
            if chave_t.lower() in imp["titulo"].lower():
                orgao = nome_org
        if not orgao:
            natureza = {"Judicial": "Leilão judicial", "Extrajudicial": "Leilão extrajudicial"}.get(meta.get("natureza"), "Leilão")
            orgao = f"{natureza} · {fonte['nome']}"
        return {
            "id": f"{dom.replace('www.', '').split('.')[0]}-{lid}",
            "titulo": titulo_bonito(imp["titulo"]),
            "org": orgao,
            "fonte": fonte,
            "site": f"https://{dom}/leiloes/{lid}",
            "siteNome": dom.replace("www.", ""),
            "edital": sl.edital_de(meta.get("docs", [])),
            "pracas": pracas,
            "atual": atual,
            "modo": modo_bonito(imp["modalidade"]),
            "visita": meta.get("visita", ""),
            "retirada": meta.get("retirada", ""),
            "lotes": lotes,
        }


def regra_custo(cfg, titulo):
    for r in cfg.get("regras_custo", []):
        if any(c.lower() in titulo.lower() for c in r["chaves"]):
            return {k: v for k, v in r.items() if k != "chaves"}
    return {}


def montar_saida(coletas, cfg, fipe, momento):
    leiloes, locais, lotes, idx_local = [], [], [], {}
    fipe_ref = ""
    for res in coletas:
        for a in res["leiloes"]:
            f = a["fonte"]
            ai = len(leiloes)
            selo_txt = f.get("selo_texto") or (
                f"Matrícula {f['matricula']} na lista oficial de leiloeiros da JUCERJA." if f.get("selo") == "junta"
                else f"Matrícula {f['matricula']} informada no edital.")
            leiloes.append({
                "id": a["id"], "titulo": a["titulo"], "org": a["org"], "leiloeiro": f["leiloeiro"],
                "titLei": f.get("titulo_leiloeiro", "Leiloeiro"), "mat": f["matricula"],
                "selo": "ok" if f.get("selo") == "junta" else "edital", "seloTxt": selo_txt,
                "site": a["site"], "siteNome": a["siteNome"], "edital": a["edital"],
                "fim": a["atual"]["fim"].isoformat(), "hora": a["atual"]["com_hora"],
                "pracas": [{"n": p["nome"], "fim": p["fim"].isoformat(), "hora": p["com_hora"]} for p in a["pracas"]],
                "modo": a["modo"], "visita": a["visita"], "retirada": a["retirada"],
                "custo": regra_custo(cfg, a["titulo"]), "fonte": f["nome"],
            })
            for l in a["lotes"]:
                loc = l["local"]
                lk = (loc["nome"], loc["lat"], loc["lon"])
                if lk not in idx_local:
                    idx_local[lk] = len(locais)
                    locais.append({"nome": loc["nome"], "end": loc["endereco"], "lbl": loc["rotulo"],
                                   "lat": loc["lat"], "lon": loc["lon"], "aprox": loc["aprox"]})
                v = l["v"]
                fp = fipe.buscar(v) if fipe else None
                if fp:
                    fipe_ref = fipe_ref or fp["ref"]
                lotes.append([ai, l["chave"], v["tipo"], v["marca"], v["modelo"], v["ano_fab"], v["ano_mod"], v["cor"],
                              v["combustivel"], 1 if v["sem_motor"] else 0, l["obs"], l["inicial"], l["atual"], l["lances"],
                              fp["valor"] if fp else None, fp["modelo"] if fp else None, fp["ano"] if fp else None,
                              idx_local[lk], 1 if v["blindado"] else 0])
    return {
        "gerado_em": momento.isoformat(),
        "fipe_ref": fipe_ref,
        "leiloes": leiloes,
        "locais": locais,
        "lotes": lotes,
        "fontes": [{"nome": r["nome"], "site": r["dominio"].replace("www.", ""), "ok": r["ok"],
                    "leiloes": len(r["leiloes"]), "lotes": sum(len(a["lotes"]) for a in r["leiloes"])} for r in coletas],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default=str(RAIZ / "site" / "data" / "leiloes.json"))
    ap.add_argument("--estado", default=str(RAIZ / "dados" / "estado.json"))
    ap.add_argument("--status", default=str(RAIZ / "dados" / "status.json"))
    ap.add_argument("--sem-fipe", action="store_true")
    ap.add_argument("--so", help="só estes domínios, separados por vírgula")
    args = ap.parse_args(argv)

    momento = agora()
    cfg = json.load(open(RAIZ / "config" / "fontes.json"))
    estado = ler_json(args.estado, {"leiloes": {}})
    estado.setdefault("leiloes", {})
    geo = Geo(RAIZ / "dados" / "municipios.json", RAIZ / "config" / "locais.json")
    fontes = cfg["plataforma_suporte_leiloes"]
    if args.so:
        fontes = [f for f in fontes if f["dominio"] in args.so.split(",")]

    coleta = Coleta(cfg, estado, geo, momento)
    with cf.ThreadPoolExecutor(max_workers=len(fontes)) as ex:
        coletas = list(ex.map(lambda f: _seguro(coleta, f), fontes))

    fipe = None if args.sem_fipe else Fipe(str(RAIZ / "dados" / "fipe_cache.json"))
    saida = montar_saida(coletas, cfg, fipe, momento)
    if fipe:
        fipe.salvar()

    anterior = ler_json(args.status, {})
    problemas = []
    for r in coletas:
        if not r["ok"]:
            problemas.append(f"{r['nome']}: {r['erro']}")
    if not saida["lotes"]:
        problemas.append("nenhum veículo encontrado em nenhuma fonte")
    lotes_antes = anterior.get("total_lotes") or 0
    if lotes_antes >= 40 and len(saida["lotes"]) < lotes_antes * 0.3:
        problemas.append(f"o total de veículos caiu de {lotes_antes} para {len(saida['lotes'])}")
    status = {
        "gerado_em": momento.isoformat(),
        "ok": not problemas,
        "problemas": problemas,
        "total_leiloes": len(saida["leiloes"]),
        "total_lotes": len(saida["lotes"]),
        "com_fipe": sum(1 for x in saida["lotes"] if x[14]),
        "consultas_fipe": fipe.consultas if fipe else 0,
        "fipe_limitada": bool(fipe and fipe.bloqueada),
        "pedidos_aos_sites": coleta.cliente.pedidos,
        "fontes": [{"nome": r["nome"], "dominio": r["dominio"], "ok": r["ok"], "erro": r["erro"],
                    "avisos": r["avisos"][:15], "paginas_lidas": r["paginas_lidas"],
                    "leiloes_com_veiculos": len(r["leiloes"]),
                    "lotes": sum(len(a["lotes"]) for a in r["leiloes"])} for r in coletas],
    }
    gravar_json(args.saida, saida, compacto=True)
    gravar_json(args.estado, estado)
    gravar_json(args.status, status)
    gravar_json(Path(args.saida).with_name("status.json"), status)
    print(json.dumps({k: v for k, v in status.items() if k != "fontes"}, ensure_ascii=False, indent=1))
    for f in status["fontes"]:
        print(f"- {f['nome']}: {'ok' if f['ok'] else 'FALHOU'} · {f['leiloes_com_veiculos']} leilões · {f['lotes']} veículos"
              + (f" · {f['erro']}" if f["erro"] else "") + (f" · {len(f['avisos'])} avisos" if f["avisos"] else ""))
    return 0 if status["ok"] else 2


def _seguro(coleta, fonte):
    try:
        return coleta.fonte(fonte)
    except Exception:
        return {"dominio": fonte["dominio"], "nome": fonte["nome"], "ok": False,
                "erro": "erro inesperado: " + traceback.format_exc()[-300:], "avisos": [], "paginas_lidas": 0, "leiloes": []}


if __name__ == "__main__":
    sys.exit(main())
