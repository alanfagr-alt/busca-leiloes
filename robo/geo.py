"""Localização dos lotes: pátio conhecido (config/locais.json) ou centro do município."""
import json
import re

from .veiculos import sem_acento

ESTADOS = {"ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA", "CEARA": "CE", "DISTRITO FEDERAL": "DF",
           "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA", "MATO GROSSO DO SUL": "MS", "MATO GROSSO": "MT",
           "MINAS GERAIS": "MG", "PARANA": "PR", "PARAIBA": "PB", "PARA": "PA", "PERNAMBUCO": "PE", "PIAUI": "PI",
           "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RIO DE JANEIRO": "RJ", "RONDONIA": "RO", "RORAIMA": "RR",
           "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE", "TOCANTINS": "TO"}


def chave(s):
    return re.sub(r"[^A-Z0-9 ]", " ", sem_acento(s).upper()).split()


class Geo:
    def __init__(self, caminho_municipios, caminho_locais):
        self.mun = {}
        self.capital = {}
        self.por_uf = {}
        for nome, uf, lat, lon, ibge, cap in json.load(open(caminho_municipios)):
            k = " ".join(chave(nome))
            self.mun[(k, uf)] = {"nome": nome, "uf": uf, "lat": lat, "lon": lon}
            self.por_uf.setdefault(uf, {})[k] = self.mun[(k, uf)]
            if cap:
                self.capital[uf] = self.mun[(k, uf)]
        self.patios = json.load(open(caminho_locais))

    def municipio(self, nome, uf):
        return self.mun.get((" ".join(chave(nome)), uf))

    def de_localizacao(self, texto):
        """'Rio de Janeiro / RJ' -> município."""
        m = re.match(r"\s*(.+?)\s*/\s*([A-Z]{2})\s*$", texto or "")
        return self.municipio(m.group(1), m.group(2)) if m else None

    def no_texto(self, texto):
        """Procura 'Cidade/UF', 'Cidade - UF' ou o nome de um estado num texto livre."""
        t = texto or ""
        for m in re.finditer(r"([A-Za-zÀ-ú' ]{3,60}?)\s*(?:/|-|–|,)\s*([A-Z]{2})\b", t):
            uf = m.group(2)
            if uf not in self.por_uf:
                continue
            toks = chave(m.group(1))
            for i in range(len(toks)):
                k = " ".join(toks[i:])
                if k in self.por_uf[uf]:
                    return self.por_uf[uf][k]
        # nome do estado por extenso, só logo depois de "localização do bem", "localizado em" etc.
        u = " ".join(chave(t))
        for m in re.finditer(r"\b(LOCALIZACAO DO BEM|LOCALIZAD[OA]S? (?:EM|NA|NO)|ENCONTRA SE (?:EM|NA|NO)|SITUAD[OA]S? (?:EM|NA|NO)|DEPOSITAD[OA]S? (?:EM|NA|NO))\b(.{0,120})", u):
            trecho = m.group(2)
            for nome, uf in sorted(ESTADOS.items(), key=lambda x: -len(x[0])):
                if uf in ("RJ", "PA"):
                    continue
                if re.search(r"\b" + nome + r"\b", trecho):
                    return dict(self.capital[uf], aprox_estado=True)
        return None

    def patio(self, dominio, titulo, texto):
        alvo = sem_acento(f"{titulo} {texto}").upper()
        for p in self.patios:
            if p.get("dominio") and p["dominio"] != dominio:
                continue
            if any(sem_acento(c).upper() in alvo for c in p["chaves"]):
                return p
        return None
