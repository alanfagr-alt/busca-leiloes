"""Transforma o título e a descrição de um lote em dados de veículo (marca, modelo, ano, combustível...).

Cada leiloeiro escreve de um jeito ("CHEV PRISMA 1.4MT LT- 2015/ 2014 -GAS/ALC/GN", "Honda/Cg 160 Titan",
"VEÍCULO AUTOMOTOR, MARCA/MODELO FORD/COURIER 1.6L"), então aqui ficam as regras que reconhecem os formatos.
Placa, chassi e Renavam são sempre retirados do texto que vai para o site.
"""
import re
import unicodedata

# marca: (nome exibido, nome na FIPE, tipo provável: "c" carro, "m" moto, "?" depende do modelo)
MARCAS = {
    "CHEVROLET": ("Chevrolet", "GM - Chevrolet", "c"), "CHEV": ("Chevrolet", "GM - Chevrolet", "c"),
    "GM": ("Chevrolet", "GM - Chevrolet", "c"), "VOLKSWAGEN": ("Volkswagen", "VW - VolksWagen", "c"),
    "VW": ("Volkswagen", "VW - VolksWagen", "c"), "FIAT": ("Fiat", "Fiat", "c"), "FORD": ("Ford", "Ford", "c"),
    "RENAULT": ("Renault", "Renault", "c"), "HYUNDAI": ("Hyundai", "Hyundai", "c"), "TOYOTA": ("Toyota", "Toyota", "c"),
    "NISSAN": ("Nissan", "Nissan", "c"), "PEUGEOT": ("Peugeot", "Peugeot", "c"), "CITROEN": ("Citroën", "Citroën", "c"),
    "JEEP": ("Jeep", "Jeep", "c"), "KIA": ("Kia", "Kia Motors", "c"), "MITSUBISHI": ("Mitsubishi", "Mitsubishi", "c"),
    "MMC": ("Mitsubishi", "Mitsubishi", "c"), "AUDI": ("Audi", "Audi", "c"), "BMW": ("BMW", "BMW", "?"),
    "MERCEDES-BENZ": ("Mercedes-Benz", "Mercedes-Benz", "c"), "MERCEDES BENZ": ("Mercedes-Benz", "Mercedes-Benz", "c"),
    "MERCEDES": ("Mercedes-Benz", "Mercedes-Benz", "c"), "M.BENZ": ("Mercedes-Benz", "Mercedes-Benz", "c"),
    "MBENZ": ("Mercedes-Benz", "Mercedes-Benz", "c"), "LAND ROVER": ("Land Rover", "Land Rover", "c"),
    "LR": ("Land Rover", "Land Rover", "c"), "JAC": ("JAC", "JAC", "c"), "CHERY": ("Chery", "CHERY", "c"),
    "CAOA CHERY": ("Chery", "CHERY", "c"), "BYD": ("BYD", "BYD", "c"), "VOLVO": ("Volvo", "Volvo", "c"),
    "SCANIA": ("Scania", "Scania", "c"), "IVECO": ("Iveco", "Iveco", "c"), "AGRALE": ("Agrale", "Agrale", "c"),
    "SUZUKI": ("Suzuki", "Suzuki", "?"), "JTA": ("Suzuki", "SUZUKI", "m"), "HONDA": ("Honda", "Honda", "?"),
    "YAMAHA": ("Yamaha", "YAMAHA", "m"), "DAFRA": ("Dafra", "DAFRA", "m"), "TRAXX": ("Traxx", "TRAXX", "m"),
    "SHINERAY": ("Shineray", "SHINERAY", "m"), "HAOJUE": ("Haojue", "HAOJUE", "m"), "KASINSKI": ("Kasinski", "KASINSKI", "m"),
    "SUNDOWN": ("Sundown", "SUNDOWN", "m"), "ROYAL ENFIELD": ("Royal Enfield", "ROYAL ENFIELD", "m"),
    "KAWASAKI": ("Kawasaki", "KAWASAKI", "m"), "TRIUMPH": ("Triumph", "TRIUMPH", "m"), "HARLEY": ("Harley-Davidson", "HARLEY-DAVIDSON", "m"),
    "HARLEY-DAVIDSON": ("Harley-Davidson", "HARLEY-DAVIDSON", "m"), "JTZ": ("JTZ", "JTZ", "m"), "IROS": ("Iros", "IROS", "m"),
    "AVELLOZ": ("Avelloz", "AVELLOZ", "m"), "MOTTU": ("Mottu", "MOTTU", "m"), "BULL": ("Bull", "BULL", "m"),
    "VOLTZ": ("Voltz", "VOLTZ", "m"), "PIAGGIO": ("Piaggio", "PIAGGIO", "m"), "DUCATI": ("Ducati", "DUCATI", "m"),
    "CAOA": ("Chery", "CHERY", "c"), "RAM": ("RAM", "RAM", "c"), "DODGE": ("Dodge", "Dodge", "c"),
    "CHRYSLER": ("Chrysler", "Chrysler", "c"), "MINI": ("Mini", "MINI", "c"), "PORSCHE": ("Porsche", "Porsche", "c"),
    "SMART": ("Smart", "Smart", "c"), "SSANGYONG": ("SsangYong", "SSANGYONG", "c"), "LIFAN": ("Lifan", "LIFAN", "c"),
    "EFFA": ("Effa", "EFFA", "c"), "TROLLER": ("Troller", "TROLLER", "c"), "GURGEL": ("Gurgel", "Gurgel", "c"),
}
MODELOS_MOTO = re.compile(
    r"\b(CG|CB|CBX|CBR|NXR|XRE|XR|BIZ|POP|BROS|PCX|ELITE|LEAD|ADV|SAHARA|TWISTER|TITAN|FAN|START|FALCON|HORNET|"
    r"NC|CRF|SH|DIO|C ?100|C ?125|YS|YBR|XTZ|FAZER|FACTOR|CROSSER|NEO|NMAX|N-MAX|XMAX|LANDER|TENERE|MT|FZ\d*|"
    r"EN ?125|YES|INTRUDER|BURGMAN|GSX|V-STROM|HIMALAYAN?|METEOR|CLASSIC|G ?310|F ?\d{3,4} ?GS|R ?1250|HUNTER|"
    r"JH ?\d+|JL ?\d+|SPEED|CITYCOM|NEXT|APACHE|KANSAS|MIRAGE|COMET|ZIG|WEB|JET|PHOENIX|XY ?\d+)\b")
IMOVEL = re.compile(r"\b(apartament|apto|sala comercial|sala\b|terreno|im[óo]vel|pr[ée]dio|casa\b|loja\b|galp[ãa]o|gleba|fazenda|lote de terreno|"
                    r"cota imobili|direito e a[çc][ãa]o)", re.I)
SUCATA = re.compile(r"\bsucatas?\b|\bfragment|pe[çc]as avulsas|\bp/ ?desmonte|\bdesmonte\b", re.I)
PALAVRA_VEICULO = re.compile(r"\b(ve[íi]culo|v[ée]iculo|autom[óo]vel|automotor|motocicleta|motoneta|ciclomotor|caminh[ãa]o|caminhonete|"
                             r"utilit[áa]rio|camioneta|[ôo]nibus|micro-?[ôo]nibus|furg[ãa]o|moto\b)", re.I)
CORES = ["Branca", "Branco", "Preta", "Preto", "Prata", "Cinza", "Vermelha", "Vermelho", "Azul", "Verde", "Amarela", "Amarelo",
         "Bege", "Marrom", "Laranja", "Dourada", "Dourado", "Rosa", "Roxa", "Roxo", "Vinho", "Grená", "Fantasia"]


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


RE_PLACA = re.compile(r"\b(?!(?:ANO|COR|MOD|NUM|KMS?|LOTE|ART|LEI|FLS)\b)[A-Z]{3}-?\s?\d[A-Z0-9]\d{2}\b(?:\s*/\s*[A-Z]{2})?", re.I)
RE_CHASSI = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
RE_SENSIVEL = re.compile(r"(?i)\b(placa|chassis?|renavam|motor n[ºo°]?|n[ºo°] do motor|motor)\s*(?:n[ºo°.]*\s*)?:?\s*[A-Z0-9*\-./ ]{4,25}")


def limpar_sensiveis(s):
    s = RE_CHASSI.sub("", s or "")
    s = re.sub(r"(?i)\b(?:placa|chassis?|chassi n[ºo°]|renavam)\s*(?:n[ºo°.]*)?\s*:?\s*[A-Z0-9\-./]{5,25}\*?", "", s)
    s = re.sub(r"(?i)\bmotor\s*:?\s*[A-Z0-9]{2,}[A-Z0-9*\-]*\d[A-Z0-9*\-]*", "", s)
    s = RE_PLACA.sub("", s)
    s = re.sub(r"\s*\|\s*(?=\||$)", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" ,;|-")


def _anos(texto):
    t = texto
    m = re.search(r"\b((?:19|20)\d{2})\s*/\s*((?:19|20)\d{2})\b", t)
    if m:
        a, b = sorted((int(m.group(1)), int(m.group(2))))
        return a, b
    fab = re.search(r"(?i)ano\s+(?:de\s+)?fabrica[çc][ãa]o\s*:?\s*((?:19|20)\d{2})", t)
    mod = re.search(r"(?i)ano\s+(?:de\s+)?modelo\s*:?\s*((?:19|20)\d{2})", t)
    if fab or mod:
        f = int(fab.group(1)) if fab else int(mod.group(1))
        mo = int(mod.group(1)) if mod else f
        return min(f, mo), max(f, mo)
    m = re.search(r"\b(\d{2})\s*/\s*(\d{2})\b", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 0 <= b - a <= 1 or (a == 99 and b == 0):
            conv = lambda x: 2000 + x if x <= 40 else 1900 + x
            return conv(a), conv(b)
    m = re.search(r"(?i)\bano\s*:?\s*((?:19|20)\d{2})\b", t) or re.search(r"\b((?:19[5-9]|20[0-3])\d)\b", t)
    if m:
        y = int(m.group(1))
        return y, y
    return None, None


def _combustivel(t):
    u = sem_acento(t).upper()
    if re.search(r"ELETRI|HIBRID", u):
        return "Híbrido ou elétrico"
    if re.search(r"GAS\w*\s*/\s*ALC\w*\s*/\s*GN|GNV|\bGN\b", u):
        return "Flex e GNV" if "ALC" in u or "FLEX" in u else "Gasolina e GNV"
    if re.search(r"ALC\w*\s*/\s*GAS|GAS\w*\s*/\s*ALC|FLEX", u):
        return "Flex"
    if "DIESEL" in u:
        return "Diesel"
    if re.search(r"\bGASOLINA\b", u):
        return "Gasolina"
    if re.search(r"\bALCOOL\b", u):
        return "Álcool"
    return ""


FEMININO = {"Branco": "Branca", "Preto": "Preta", "Vermelho": "Vermelha", "Amarelo": "Amarela", "Dourado": "Dourada", "Roxo": "Roxa"}


def _cor(t):
    for m in re.finditer(r"(?i)\bcor(?:\s+predominante)?\b\s*:?\s*([A-Za-zÀ-ú]+)", t):
        c = m.group(1).capitalize()
        if c in CORES:
            return FEMININO.get(c, c)
    u = sem_acento(t).upper()
    for c in CORES:
        if re.search(r"\b" + sem_acento(c).upper() + r"\b", u):
            return FEMININO.get(c, c)
    return ""


def _achar_marca(texto):
    """Devolve (chave da marca, posição onde o modelo começa)."""
    u = sem_acento(texto).upper()
    u = re.sub(r"\bI\s*/\s*", " ", u)  # "I/BMW" (importado)
    melhor = None
    for chave in sorted(MARCAS, key=len, reverse=True):
        for m in re.finditer(r"(?<![A-Z0-9])" + re.escape(chave) + r"(?![A-Z0-9])", u):
            if melhor is None or m.start() < melhor[1]:
                melhor = (chave, m.start(), m.end())
            break
    if not melhor:
        return None, None, u
    return melhor[0], melhor[2], u


CORTES_MODELO = re.compile(
    r"(?i)(\s-\s|,|\(|\||\bplaca\b|\bano\b|\bcor\b|\brenavam\b|\bchassi|\bcombust|\bcategoria\b|\btipo\b|"
    r"\b(?:19|20)\d{2}\b|\b\d{2}/\d{2}\b|-\s*(?:19|20)\d{2}|\s-(?=[A-Z]))")
LIXO_MODELO = re.compile(r"(?i)\b(modelo|mod\.?|marca|ve[íi]culo|automotor|autom[óo]vel|motocicleta|\(suv\)|suv|blindado|"
                         r"caminhonete|caminh[ãa]o|utilit[áa]rio esportivo|flex|carroceria fechada|carroceria aberta|carroceria)\b")


def _modelo(u, ini):
    resto = re.sub(r"\(\s*SUV\s*\)", " ", u[ini:], flags=re.I)
    for _ in range(3):
        resto = re.sub(r"^[\s/\-:,.;]+", "", resto)
        resto = re.sub(r"(?i)^(?:modelo|mod\.?|marca)\s*:?\s*", "", resto)
        resto = re.sub(r"^(?:CHEVROLET|CHEV)\b\s*[/,]?\s*", "", resto)
    m = CORTES_MODELO.search(resto)
    modelo = resto[: m.start()] if m else resto
    modelo = LIXO_MODELO.sub(" ", modelo)
    modelo = re.sub(r"[/]+", " ", modelo)
    modelo = re.sub(r"\s+", " ", modelo).strip(" .-,:")
    toks = modelo.split()
    while len(toks) > 1 and (toks[0] in MARCAS or toks[0] in ("I", "IMP")):
        toks = toks[1:]
    return " ".join(toks)[:40]


def _modelo_da_descricao(desc):
    m = re.search(r"(?i)\bmodelo\s*:\s*(.+?)(?=\s+(?:tipo|cor|ano|placa|combust[ií]vel|marca|renavam|chassi|trata-se)\b|[|;]|$)", desc or "")
    if not m:
        return ""
    u = sem_acento(m.group(1)).upper()
    u = re.sub(r"\bI\s*/\s*", " ", u)
    chave, ini, u2 = _achar_marca(u)
    return _modelo(u2, ini) if chave else _modelo(u, 0)


def _cap(s):
    out = []
    for t in s.split():
        if any(ch.isdigit() for ch in t) or len(t) <= 3:
            out.append(t.upper())
        else:
            out.append(t.capitalize())
    return " ".join(out)


def interpretar(titulo, desc):
    """Devolve um dicionário com os dados do veículo, ou None se o lote não for um veículo vendável."""
    texto = f"{titulo} | {desc}"
    if SUCATA.search(texto):
        return None
    if IMOVEL.search(titulo) and not PALAVRA_VEICULO.search(titulo):
        return None
    chave, ini, u = _achar_marca(titulo)
    fonte = u
    if not chave:
        chave, ini, u = _achar_marca(texto)
        fonte = u
    if not chave:
        return None
    anos = _anos(texto)
    if anos == (None, None) and not PALAVRA_VEICULO.search(texto):
        return None
    if anos[1] and not (1950 <= anos[1] <= 2030):
        return None
    nome, fipe_marca, tipo = MARCAS[chave]
    modelo = _modelo_da_descricao(desc) or _modelo(fonte, ini)
    if not modelo:
        return None
    U = sem_acento(texto).upper()
    if tipo == "?":
        tipo = "m" if (MODELOS_MOTO.search(modelo.upper()) or re.search(r"MOTOCICLETA|MOTONETA", U)) else "c"
    if re.search(r"\bMOTOCICLETA\b|\bMOTONETA\b", U):
        tipo = "m"
    caminhao = bool(re.search(r"CAMINH[AÃ]O|\bONIBUS\b|MICRO-?ONIBUS|CARROCERIA", U)) or (nome == "Mercedes-Benz" and re.fullmatch(r"\d{3,4}.*", modelo))
    sem_motor = bool(re.search(r"SEM MOTOR|MOTOR (?:SERA )?RETIRADO", U))
    fab, mod = anos
    return {
        "tipo": tipo,
        "marca": nome,
        "marca_fipe": fipe_marca,
        "fipe_tipo": "caminhoes" if caminhao else ("motos" if tipo == "m" else "carros"),
        "modelo": _cap(modelo),
        "modelo_busca": modelo,
        "ano_fab": fab,
        "ano_mod": mod,
        "combustivel": _combustivel(texto),
        "cor": _cor(texto),
        "sem_motor": sem_motor,
        "blindado": "BLINDADO" in U,
    }


SEGMENTO_INUTIL = re.compile(
    r"(?i)^(?:(?:19|20)\d{2}\s*/\s*(?:19|20)\d{2}|(?:placa|chassis?|renavam|motor)\s*:?|gasolina|alco/gasol|[aá]lcool/gasolina|"
    r"diesel|flex|gas/alc/gn|gasol/gnv|ve[íi]culo conservado\.?|conservado(?: sem motor)?|" + "|".join(CORES) + r")$")


def observacao(titulo, desc, limite=260):
    """Texto curto para o site, sem placa, chassi, Renavam e sem repetir o que já aparece no título."""
    t = limpar_sensiveis(titulo or "")
    d = desc or ""
    d = re.sub(r"(?i)\(?imagem meramente ilustrativa\)?", "", d)
    d = re.sub(r"(?i)\b(Primeiro|Segundo|Terceiro) Leil[ãa]o:.*?(?=(?:Primeiro|Segundo|Terceiro) Leil[ãa]o:|$)", "", d)
    d = re.sub(r"(?i)^\s*modelo:\s*.+?(?=\btrata-se\b|\blocaliza[çc][ãa]o\b|\bvalor\b|$)", "", d)
    d = re.sub(r"(?i)trata-se de um ve[íi]culo automotor,[^.]*\.\s*", "", d)
    d = re.sub(r"(?i)\bano(?:\s+de)?\s+fabrica[çc][ãa]o\s*/\s*(?:ano\s+)?modelo\s*:?\s*(?:19|20)\d{2}(?:\s*/\s*(?:19|20)\d{2})?", "", d)
    d = re.sub(r"(?i)\b(?:ano/modelo|ano modelo|ano)\s*:?\s*(?:19|20)\d{2}(?:\s*/\s*(?:19|20)\d{2})?", "", d)
    d = re.sub(r"(?i)\b(?:cor(?: predominante)?|combust[íi]vel)\s*:\s*[A-Za-zÀ-ú/]+", "", d)
    d = re.sub(r"\([^()]*\breais\)", "", d)
    d = limpar_sensiveis(d)
    partes = []
    for seg in re.split(r"\s*\|\s*", d):
        seg = seg.strip(" ,;.-")
        if not seg or SEGMENTO_INUTIL.match(seg) or seg.lower() == t.lower() or seg.lower() in t.lower():
            continue
        partes.append(seg)
    d = ". ".join(partes)
    d = re.sub(r"(?i)\b(?:placa|chassis?|renavam|motor)\s*(?:n[ºo°.]*)?\s*[:.]?\s*(?=[,.;]|$)", "", d)
    d = re.sub(r"(?:\s*,\s*){2,}", ", ", d)
    d = re.sub(r"\s+([,.;:])", r"\1", d)
    d = re.sub(r"([,.;:])(?=[^\s\d])", r"\1 ", d)
    d = re.sub(r"^\s*(?:\(?\s*(?:0?1|um)\s*\)?\s*[°ºo)]*\s*)+", "", d, flags=re.I)
    d = re.sub(r"\s{2,}", " ", d).strip(" ,;|-.")
    if re.fullmatch(r"(?i)(ve[íi]culo\s+)?conservad[oa](\s+sem motor)?", d):
        return ""
    if d and sum(c.isupper() for c in d) > 0.6 * sum(c.isalpha() for c in d):
        d = d.lower()
        d = re.sub(r"(^|[.!?]\s+)([a-zà-ú])", lambda m: m.group(1) + m.group(2).upper(), d)
    if len(d) > limite:
        d = d[: limite - 1].rsplit(" ", 1)[0] + "…"
    return d
