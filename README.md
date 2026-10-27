# Mapa das Eleições Gerais (2018–2026)

Mapa interativo (modo escuro) dos resultados das **eleições gerais de 2018, 2022 e 2026** (presidente, governador, senador e deputados).

- **Eleições** (abas no topo): 2018, 2022 e 2026, 1º e 2º turno (abre no 2º turno de 2026). As métricas de variação comparam com o mesmo turno da eleição anterior (2022 × 2018, 2026 × 2022). No mapa de presidente, o PT é comparado com o partido de Bolsonaro/direita em cada eleição (PSL em 2018, PL em 2022 e 2026).

- **2026 2º turno:** resultado final, da API de resultados do TSE (`tools/baixar_2026_2.py` baixa os arquivos de cada UF e de cada par município-zona; `tools/build_2026_2.py` monta `data/2026-2/`). Município = soma das suas zonas, zona = soma dos seus municípios; a soma das zonas foi conferida com o arquivo de cada UF e a soma das UFs + exterior com o total do Brasil. No nível Seção, por enquanto só há participação (aptos, comparecimento, brancos, nulos, do detalhe por seção dos dados abertos): o TSE ainda não publicou os votos por candidato em cada seção do 2º turno.
- **Ao vivo (durante a apuração):** o app ainda tem o modo ao vivo usado na noite da eleição (estados a cada 15 s, Brasil = soma dos estados + exterior, municípios aos poucos e na hora ao clicar, modo de mapa *Apuração*). Para reativá-lo numa próxima eleição, basta acrescentar `live: {...}` à eleição em `ELECTIONS` (ver comentário em `app.js`).
- **Níveis:** País, Estado, Município, Zona eleitoral e Seção.
  - Zona: o TSE não publica o desenho das zonas, então a área de cada zona é aproximada (polígonos de Voronoi dos locais de votação, recortados pelos limites dos municípios).
  - Seção: um ponto por prédio de votação. Seções no mesmo local ficam agrupadas, assim como locais com o mesmo nome no mesmo município a até 300 m (no exterior, mesmo nome ou endereço na mesma cidade).
  - O *Exterior* é um círculo no Atlântico. No nível Seção, o círculo some e cada local de votação no exterior aparece no próprio mapa, na posição real (o mapa mostra os países ao fundo e permite afastar o zoom até o mundo inteiro). O TSE não publica essas coordenadas; elas foram geocodificadas pelo endereço (`tools/geocode_exterior.py`).
- **Ruas (OpenStreetMap):** contorno claro das ruas em todos os níveis (por cima das cores; no nível Seção, ao fundo), com opção para ligar/desligar no painel de filtros.
- **Busca de endereços** (topo): pesquisa no OpenStreetMap (Nominatim) ao apertar Enter; o mapa dá zoom no resultado e marca um alfinete.
- **Modos de mapa** (canto inferior esquerdo):
  - votos válidos e % de votos válidos sobre o eleitorado;
  - votos (comparecimento) e % de comparecimento;
  - variação de cada uma dessas métricas em relação à eleição anterior (mesmo turno);
  - presidente (PT × PL, ou PSL em 2018) e a variação desde a eleição anterior;
  - governador (partido mais votado, com a intensidade da cor pela margem de vitória).
- **Escalas:** os limites saem dos dados do nível atual, não de 0%/100% fixos: percentis 2–98 em geral, 25–75 para presidente (simétrico em torno de 50%) e 95 para a margem de governador.
- **Painel lateral** (clique em um elemento): votação, eleitorado e abas por cargo, com filtros por partido e por situação do candidato.

## Estrutura

```
index.html, style.css, app.js   app estático (d3 e topojson-client em vendor/)
data/<eleição>/                 uma pasta por eleição: 2018-1, 2018-2, 2022-1, 2022-2, 2026-1, 2026-2
  summary.json                  métricas de cada elemento (Brasil, UFs, exterior, municípios, zonas)
  d/<id>.json                   detalhe por elemento (totais e votos por candidato e cargo)
  cand/<escopo>.json            candidatos (nome, número, partido, situação)
  s/, sd/                       locais de votação (pontos) e votos por local
  geo/zonas.json                áreas aproximadas das zonas daquela eleição
data/geo/                       malhas comuns: estados e municípios (IBGE) e países (Natural Earth)
tools/build.py                  gera data/2026-1/ (API de resultados + dados abertos do TSE)
tools/build_eleicao.py          gera data/<ano>-1/ e data/<ano>-2/ de 2018 e 2022 (só dados abertos do TSE)
```

## Fontes

- TSE, resultados: `resultados.tse.jus.br/oficial/ele2026` (arquivos `-u.json` por UF).
- TSE, dados abertos: `cdn.tse.jus.br/estatistica/sead/odsele/` (votação por município/zona e por seção, detalhe por seção e locais de votação de 2018, 2022 e 2026).
- IBGE, malhas: `servicodados.ibge.gov.br/api/v3/malhas`.
- Fotos dos candidatos: carregadas direto do TSE (2026: site de resultados; 2018 e 2022: DivulgaCandContas).

## Rodar localmente

```
python3 -m http.server 8000
```

Depois abra http://localhost:8000.
