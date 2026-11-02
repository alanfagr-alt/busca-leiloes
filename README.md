# Busca de leilões de veículos

Reúne num lugar só os leilões oficiais de carros e motos e mostra, para a cidade da pessoa, o que está aberto por perto, o valor atual, a comparação com a FIPE e o custo total estimado. A página é publicada em https://alanfagr-alt.github.io/busca-leiloes/ e aparece dentro do guiavagas.com.

## Como funciona

1. Quatro vezes por dia (6h07, 10h37, 14h37 e 18h37, horário de Brasília) o GitHub roda `python -m robo.montar`.
2. Os robôs leem os sites dos leiloeiros, guardam só os lotes que são veículos, limpam placa, chassi e Renavam, acham o local e cruzam com a Tabela FIPE.
3. O resultado vira `site/data/leiloes.json`, e a página (`site/index.html`) é publicada de novo com os dados novos.
4. Se alguma fonte falhar ou o total de veículos despencar, a rodada fica vermelha e um aviso ("issue") é aberto neste repositório. Quando volta ao normal, o aviso fecha sozinho.

O robô se identifica como `GuiaVagasLeiloesBot`, espera entre um pedido e outro e só lê páginas públicas. Site que bloquear robô ou proibir a leitura nos termos de uso não entra: vira conversa de parceria.

## Fontes

Hoje: sete leiloeiros do RJ que usam a plataforma Suporte Leilões (`config/fontes.json`). Todos têm as mesmas páginas públicas, então um robô só (`robo/suporte_leiloes.py`) cobre todos.

Para incluir outro leiloeiro da mesma plataforma, basta acrescentar uma entrada em `config/fontes.json` com o domínio, o nome e a matrícula na JUCERJA.

Pátios conhecidos (com endereço exato) ficam em `config/locais.json`. Sem pátio cadastrado, o veículo vai para o centro do município informado pelo leiloeiro.

## Arquivos

- `robo/` coletores, leitura dos lotes (`veiculos.py`), FIPE (`fipe.py`) e montagem (`montar.py`)
- `config/` fontes, pátios e regras de custo
- `dados/estado.json` memória entre rodadas (leilões encerrados, lance inicial de cada lote)
- `dados/status.json` resultado da última rodada, fonte por fonte
- `dados/fipe_cache.json` respostas da FIPE guardadas por 30 dias
- `site/` a página publicada
