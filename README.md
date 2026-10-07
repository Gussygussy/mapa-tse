# Mapa Eleições 2026

Mapa interativo (modo escuro) dos resultados do **1º turno das eleições gerais de 2026**, com comparação com 2022.

- **Níveis:** País, Estado, Município, Zona eleitoral e Seção.
  - Zona: o TSE não publica o desenho das zonas, então a área de cada zona é aproximada (polígonos de Voronoi dos locais de votação, recortados pelos limites dos municípios).
  - Seção: um ponto por local de votação; seções no mesmo local ficam agrupadas.
  - O *Exterior* é um círculo no Atlântico. No nível Seção ele é dividido em bolhas, uma por cidade (área proporcional ao eleitorado), porque o TSE não publica coordenadas dos locais no exterior.
- **Ruas (OpenStreetMap):** contorno claro das ruas em todos os níveis (por cima das cores; no nível Seção, ao fundo), com opção para ligar/desligar no painel de filtros.
- **Modos de mapa** (canto inferior esquerdo):
  - votos válidos e % de votos válidos sobre o eleitorado;
  - votos (comparecimento) e % de comparecimento;
  - variação de cada uma dessas métricas em relação a 2022;
  - presidente (PT × PL) e a variação PT × PL desde 2022;
  - governador (partido mais votado, com a intensidade da cor pela margem de vitória).
- **Escalas:** os limites saem dos dados do nível atual, não de 0%/100% fixos: percentis 2–98 em geral, 25–75 para presidente (simétrico em torno de 50%) e 95 para a margem de governador.
- **Painel lateral** (clique em um elemento): votação, eleitorado e abas por cargo, com filtros por partido e por situação do candidato.

## Estrutura

```
index.html, style.css, app.js   app estático (d3 e topojson-client em vendor/)
data/summary.json               métricas de cada elemento (Brasil, UFs, exterior, municípios, zonas)
data/d/<id>.json                detalhe por elemento (totais e votos por candidato e cargo)
data/cand/<escopo>.json         candidatos (nome, número, partido, situação)
data/s/<uf>.json, data/sd/<mun>.json   locais de votação (pontos) e votos por local
data/geo/                       malhas do IBGE (estados e municípios) e áreas aproximadas das zonas
tools/build.py                  gera data/ a partir dos arquivos brutos do TSE e do IBGE
```

## Fontes

- TSE, resultados: `resultados.tse.jus.br/oficial/ele2026` (arquivos `-u.json` por UF).
- TSE, dados abertos: `cdn.tse.jus.br/estatistica/sead/odsele/` (votação por município/zona e por seção, detalhe por seção, locais de votação, dados de 2022).
- IBGE, malhas: `servicodados.ibge.gov.br/api/v3/malhas`.
- Fotos dos candidatos: carregadas direto do TSE.

## Rodar localmente

```
python3 -m http.server 8000
```

Depois abra http://localhost:8000.
