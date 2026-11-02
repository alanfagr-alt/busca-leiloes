"""Cliente HTTP educado: identifica o robô, espera entre pedidos ao mesmo site e tenta de novo em falha passageira."""
import threading
import time
from urllib.parse import urlparse

import requests

UA = "GuiaVagasLeiloesBot/1.0 (+https://guiavagas.com/leiloes-de-veiculos-rj/)"


class Cliente:
    def __init__(self, intervalo=1.0, timeout=45):
        self.sessao = requests.Session()
        self.sessao.headers.update({"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
        self.intervalo = intervalo
        self.timeout = timeout
        self._proximo = {}
        self._trava = threading.Lock()
        self.pedidos = 0

    def _aguardar_vez(self, host):
        with self._trava:
            agora = time.monotonic()
            vez = max(agora, self._proximo.get(host, 0.0))
            self._proximo[host] = vez + self.intervalo
        espera = vez - time.monotonic()
        if espera > 0:
            time.sleep(espera)

    def get(self, url, **kw):
        host = urlparse(url).netloc
        erro = None
        for tentativa in range(3):
            self._aguardar_vez(host)
            try:
                r = self.sessao.get(url, timeout=kw.pop("timeout", self.timeout), **kw)
                self.pedidos += 1
                if r.status_code in (429, 500, 502, 503, 504):
                    erro = f"HTTP {r.status_code}"
                    time.sleep(5 * (tentativa + 1))
                    continue
                return r
            except requests.RequestException as e:
                erro = str(e)[:200]
                time.sleep(4 * (tentativa + 1))
        raise RuntimeError(f"falhou {url}: {erro}")
