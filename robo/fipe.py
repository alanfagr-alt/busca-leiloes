"""Preço de referência da Tabela FIPE pela API pública parallelum, com cache em disco.

O cache guarda cada resposta por 30 dias, então só os modelos novos geram consulta.
Se a API limitar (HTTP 429), o robô para de consultar nesta rodada e segue sem FIPE para os que faltaram.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta

import requests
from rapidfuzz import fuzz

from .http import UA
from .veiculos import sem_acento

BASE = "https://parallelum.com.br/fipe/api/v1"
VALIDADE = timedelta(days=30)

PARADAS = {"MT", "AT", "FLEX", "ES", "KS", "ED", "ESD", "ESI", "ESDI", "EX", "SED", "LT", "LTZ", "GL", "GLX", "SD", "X", "S",
           "K", "SL", "CVT", "MCA", "PLUS", "EXP", "EXPR", "AUT", "DLX", "ABS", "START", "FAN", "TITAN", "CARGO", "SPORT",
           "2P", "3", "4P", "PORTAS", "LIFE", "VH", "L", "M", "I", "V", "16V", "8V", "16", "10", "14", "15", "18", "20",
           "NOVO", "NOVA", "MPI", "20V", "HLX", "HPE", "D", "JOYE", "SENSAT", "XEI", "XLI", "SEL"}
ABREV = {"EXPR": "EXPRESSION", "SENSAT": "SENSATION", "COMF": "COMFORT", "PR": "PRESENCE", "PK": "PACK", "AUT": "AUTHENTIQUE",
         "JOYE": "JOY", "SD": "SEDAN", "EXP": "EXPRESSION"}
CILINDRADAS = {50, 100, 110, 125, 150, 155, 160, 190, 200, 250, 300, 310, 400, 410, 500, 600, 650, 660, 750, 800, 900, 1000, 1200, 1250}


def norm(s):
    s = sem_acento(s).upper().replace("/", " ").replace("-", " ")
    s = re.sub(r"(?<=[A-Z])(?=\d)|(?<=\d)(?=[A-Z])", " ", s)
    s = re.sub(r"[^A-Z0-9\. ]", " ", s)
    return " ".join(s.split())


def expandir(modelo, tipo):
    toks = []
    for i, t in enumerate(norm(modelo).split()):
        t = ABREV.get(t, t)
        prefixo_do_nome = i == 1 and re.fullmatch(r"[A-Z]{1,3}", toks[0] or "")  # HB20, C3, I30
        if tipo == "carros" and re.fullmatch(r"1[0-9]|20", t) and not prefixo_do_nome:
            t = t[0] + "." + t[1]
        toks.append(t)
    return " ".join(x for x in toks if x)


def pontuar(modelo, nome_fipe, tipo):
    a = norm(modelo)
    b = norm(nome_fipe)
    ta = a.split()
    tb = set(b.split())
    familia = [t for t in ta if t not in PARADAS and not re.fullmatch(r"[\d\.]+", t)]
    if not familia:
        familia = ta[:1]
    if not familia or (familia[0] not in tb and not any(familia[0] in x for x in tb)):
        return 0
    if tipo == "motos":
        cil = [t for t in ta if t.isdigit() and int(t) in CILINDRADAS]
        if cil and cil[0] not in tb:
            return 0
    return fuzz.token_set_ratio(a, b) + sum(3 for t in ta if t in tb)


class Fipe:
    def __init__(self, caminho_cache):
        self.caminho = caminho_cache
        self.cache = {}
        if os.path.exists(caminho_cache):
            bruto = json.load(open(caminho_cache))
            agora = datetime.now()
            for k, v in bruto.items():
                try:
                    if agora - datetime.fromisoformat(v["t"]) < VALIDADE:
                        self.cache[k] = v
                except Exception:
                    pass
        self.sessao = requests.Session()
        self.sessao.headers["User-Agent"] = UA
        self.consultas = 0
        self.bloqueada = False
        self.memo = {}

    def salvar(self):
        json.dump(self.cache, open(self.caminho, "w"), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    def _get(self, caminho):
        if caminho in self.cache:
            return self.cache[caminho]["v"]
        if self.bloqueada:
            raise LookupError("FIPE indisponível nesta rodada")
        time.sleep(0.35)
        try:
            r = self.sessao.get(BASE + caminho, timeout=30)
        except requests.RequestException:
            self.bloqueada = True
            raise LookupError("FIPE fora do ar")
        self.consultas += 1
        if r.status_code == 429:
            self.bloqueada = True
            raise LookupError("FIPE limitou as consultas")
        v = r.json() if r.status_code == 200 else None
        self.cache[caminho] = {"t": datetime.now().isoformat(timespec="seconds"), "v": v}
        return v

    def _codigo_marca(self, tipo, marca_fipe):
        marcas = self._get(f"/{tipo}/marcas") or []
        alvo = norm(marca_fipe)
        for m in marcas:
            if norm(m["nome"]) == alvo:
                return m["codigo"]
        for m in marcas:
            if alvo.split()[0] in norm(m["nome"]).split():
                return m["codigo"]
        return None

    def buscar(self, v):
        """Recebe o dicionário de veículo (robo.veiculos.interpretar) e devolve o preço FIPE ou None."""
        if not v.get("ano_mod") or v.get("sem_motor"):
            return None
        chave = (v["fipe_tipo"], v["marca_fipe"], norm(v["modelo_busca"]), v["ano_mod"], v.get("combustivel", ""))
        if chave in self.memo:
            return self.memo[chave]
        res = None
        tipos = [v["fipe_tipo"]] + (["carros"] if v["fipe_tipo"] == "caminhoes" else [])
        try:
            for tipo in tipos:
                res = self._buscar_tipo(tipo, v)
                if res:
                    break
        except LookupError:
            return None
        self.memo[chave] = res
        return res

    def _buscar_tipo(self, tipo, v):
        cod = self._codigo_marca(tipo, v["marca_fipe"])
        if not cod:
            return None
        modelos = (self._get(f"/{tipo}/marcas/{cod}/modelos") or {}).get("modelos", [])
        alvo = expandir(v["modelo_busca"], tipo)
        cands = sorted(((pontuar(alvo, m["nome"], tipo), m) for m in modelos), key=lambda t: -t[0])
        cands = [c for c in cands if c[0] >= 62][:15]
        diesel = "Diesel" in (v.get("combustivel") or "")
        for nota, m in cands:
            anos = self._get(f"/{tipo}/marcas/{cod}/modelos/{m['codigo']}/anos") or []
            codigos = [a["codigo"] for a in anos if a["codigo"].startswith(f"{v['ano_mod']}-")]
            if not codigos:
                continue
            pref = {"3": 0} if diesel else {"5": 0, "1": 1}
            codigo = sorted(codigos, key=lambda c: pref.get(c.split("-")[1], 2))[0]
            val = self._get(f"/{tipo}/marcas/{cod}/modelos/{m['codigo']}/anos/{codigo}")
            if val and val.get("Valor"):
                return {
                    "valor": float(val["Valor"].replace("R$", "").strip().replace(".", "").replace(",", ".")),
                    "modelo": val["Modelo"],
                    "ano": val["AnoModelo"],
                    "ref": val["MesReferencia"].strip(),
                }
        return None
