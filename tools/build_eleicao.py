#!/usr/bin/env python3
"""Gera os dados de uma eleição geral anterior (os dois turnos) só a partir dos CSVs do Portal de
Dados Abertos do TSE, no mesmo formato que tools/build.py gera para 2026.

Uso: python3 tools/build_eleicao.py <pasta_bruta> <ano> [ano_anterior]
  ex.: python3 tools/build_eleicao.py RAW 2018
       python3 tools/build_eleicao.py RAW 2022 2018

Saída: data/<ano>-1/ e data/<ano>-2/ (summary.json, d/, cand/, s/, sd/, geo/zonas.json).
Com ano_anterior, as métricas de variação comparam com data/<ano_anterior>-<turno>/.

A pasta bruta deve conter, em csv/:
  votacao_candidato_munzona_<ano>.zip, detalhe_votacao_munzona_<ano>.zip,
  votacao_secao_<ano>_BR.zip, votacao_secao_<ano>_<UF>.zip, detalhe_votacao_secao_<ano>.zip,
  eleitorado_local_votacao_<ano>.zip
e em raw/: mun-e006257-cm.json e mun_int.topo.json (os mesmos usados pelo build de 2026).
As coordenadas dos locais no exterior vêm de tools/exterior_coords.json (geocodificadas para
2026), casadas pelo nome/endereço do local na mesma cidade.
"""
import csv
import io
import json
import math
import os
import pickle
import random
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict

RAW = sys.argv[1]
ANO = sys.argv[2]
PREV = sys.argv[3] if len(sys.argv) > 3 else None
TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(TOOLS, '..')
CACHE = os.path.join(RAW, 'cache')
os.makedirs(CACHE, exist_ok=True)
csv.field_size_limit(10**9)

UFS = ['ac', 'al', 'ap', 'am', 'ba', 'ce', 'df', 'es', 'go', 'ma', 'mt', 'ms', 'mg', 'pa',
       'pb', 'pr', 'pe', 'pi', 'rj', 'rn', 'rs', 'ro', 'rr', 'sc', 'se', 'sp', 'to']
# partido do candidato de direita comparado com o PT no mapa de presidente
RIGHT = {'2018': ('17', 'PSL'), '2022': ('22', 'PL')}[ANO]
PT_NUM = '13'


def n(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def rows(zipname, member):
    z = zipfile.ZipFile(os.path.join(RAW, 'csv', zipname))
    with z.open(member) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, 'latin1'), delimiter=';')


def members(zipname, suffixes):
    z = zipfile.ZipFile(os.path.join(RAW, 'csv', zipname))
    return [m for m in z.namelist() if any(m.endswith(f'_{s.upper()}.csv') for s in suffixes)]


def cached(name, fn):
    p = os.path.join(CACHE, f'h{ANO}_{name}.pkl')
    if os.path.exists(p):
        with open(p, 'rb') as f:
            return pickle.load(f)
    v = fn()
    with open(p, 'wb') as f:
        pickle.dump(v, f)
    return v


def zid(uf, z):
    return f'z{uf}{int(z):04d}'


def norm(s):
    return re.sub(r'[^A-Z0-9]', '', unicodedata.normalize('NFKD', (s or '').upper()).encode('ascii', 'ignore').decode())


def status(sit, dest):
    """código de situação usado pelo app: E eleito, 2 segundo turno, S suplente, N não eleito,
    A votos anulados (candidatura indeferida/cassada)"""
    if dest and ('anulad' in dest.lower() or dest.lower().startswith('nulo')):
        return 'A'
    s = (sit or '').upper()
    if s.startswith('ELEITO'):
        return 'E'
    if '2' in s and 'TURNO' in s:
        return '2'
    if s.startswith('SUPLENTE'):
        return 'S'
    return 'N'


# ------------------------------------------------------------- municípios (códigos TSE estáveis)
cm = json.load(open(os.path.join(RAW, 'raw', 'mun-e006257-cm.json'), encoding='utf-8'))
MUNS = {}
UF_NAMES = {}
ZZ_NAMES = {}
for a in cm['abr']:
    UF_NAMES[a['cd']] = a['ds'].title().replace(' Do ', ' do ').replace(' De ', ' de ').replace(' Da ', ' da ')
    for m in a['mu']:
        if a['cd'] == 'zz':
            ZZ_NAMES[m['cd']] = m['nm']
        else:
            MUNS[m['cd']] = {'n': m['nm'], 'uf': a['cd'], 'ibge': m['cdi']}
UF_NAMES['df'] = 'Distrito Federal'
UF_NAMES['zz'] = 'Exterior'


# ------------------------------------------------------- votos por candidato (município/zona)
def load_munzona():
    """votos[turno][cargo][chave][sq] e metadados dos candidatos.
    chaves: código do município, id da zona, UF, 'zz' e 'br' (presidente)"""
    votes = {t: defaultdict(lambda: defaultdict(lambda: defaultdict(int))) for t in (1, 2)}
    meta = {}
    sit = {1: {}, 2: {}}
    zn = f'votacao_candidato_munzona_{ANO}.zip'
    for mem in members(zn, UFS + ['br']):
        for r in rows(zn, mem):
            t = n(r['NR_TURNO'])
            if t not in (1, 2):
                continue
            cg = n(r['CD_CARGO'])
            if (cg == 1) != mem.endswith('_BR.csv'):
                continue   # presidente vem do arquivo BR; os outros cargos, dos arquivos das UFs
            uf = r['SG_UF'].lower()
            sq = r['SQ_CANDIDATO']
            v = n(r['QT_VOTOS_NOMINAIS'])
            keys = ['zz'] if uf == 'zz' else [r['CD_MUNICIPIO'].zfill(5), zid(uf, r['NR_ZONA']), uf]
            if cg == 1:
                keys.append('br')
            for k in keys:
                votes[t][cg][k][sq] += v
            if sq not in meta:
                meta[sq] = [r['NM_URNA_CANDIDATO'], r['NR_CANDIDATO'], r['SG_PARTIDO'], 'N', cg,
                            r['NM_CANDIDATO'], r['DS_COMPOSICAO_COLIGACAO'] if r['DS_COMPOSICAO_COLIGACAO'] not in ('#NULO#', '#NULO') else r['SG_PARTIDO'],
                            'br' if cg == 1 else uf]
            sit[t][sq] = status(r['DS_SIT_TOT_TURNO'], r['NM_TIPO_DESTINACAO_VOTOS'])
        print('  munzona', mem, flush=True)
    flat = lambda d: {c: {k: dict(v) for k, v in dd.items()} for c, dd in d.items()}
    return {t: flat(votes[t]) for t in (1, 2)}, meta, sit


VOTES, META, SIT = cached('munzona', load_munzona)


# --------------------------------------------------------------- totais (detalhe por zona)
def load_detalhe():
    """tot[turno][cargo][chave] = [aptos, comparecimento, válidos, brancos, nulos(+anulados), anulados sub judice]"""
    tot = {t: defaultdict(lambda: defaultdict(lambda: [0] * 6)) for t in (1, 2)}
    zn = f'detalhe_votacao_munzona_{ANO}.zip'
    for mem in members(zn, UFS + ['br']):
        for r in rows(zn, mem):
            t = n(r['NR_TURNO'])
            if t not in (1, 2):
                continue
            cg = n(r['CD_CARGO'])
            if (cg == 1) != mem.endswith('_BR.csv'):
                continue
            uf = r['SG_UF'].lower()
            vals = [n(r['QT_APTOS']), n(r['QT_COMPARECIMENTO']), n(r['QT_TOTAL_VOTOS_VALIDOS']),
                    n(r['QT_VOTOS_BRANCOS']), n(r['QT_TOTAL_VOTOS_NULOS']) + n(r['QT_TOTAL_VOTOS_ANULADOS']),
                    n(r['QT_TOTAL_VOTOS_ANUL_SUBJUD'])]
            keys = ['zz'] if uf == 'zz' else [r['CD_MUNICIPIO'].zfill(5), zid(uf, r['NR_ZONA']), uf]
            if cg == 1:
                keys.append('br')
            for k in keys:
                acc = tot[t][cg][k]
                for i in range(6):
                    acc[i] += vals[i]
    return {t: {c: {k: v for k, v in d.items()} for c, d in tot[t].items()} for t in (1, 2)}


TOT = cached('detalhe', load_detalhe)

# zonas: municípios atendidos (pelo arquivo de presidente, que cobre todas as zonas)
ZONE_MUNS = defaultdict(set)
for r in rows(f'detalhe_votacao_munzona_{ANO}.zip', members(f'detalhe_votacao_munzona_{ANO}.zip', ['br'])[0]):
    if r['SG_UF'].lower() != 'zz':
        ZONE_MUNS[zid(r['SG_UF'].lower(), r['NR_ZONA'])].add(r['CD_MUNICIPIO'].zfill(5))

PRES_BY_NUM = {m[1]: sq for sq, m in META.items() if m[4] == 1}
PT_SQ, RIGHT_SQ = PRES_BY_NUM.get(PT_NUM), PRES_BY_NUM.get(RIGHT[0])
print('presidente PT', PT_SQ, 'direita', RIGHT[1], RIGHT_SQ)


# ------------------------------------------------------------------------------- saída
def out_dir(t):
    return os.path.join(ROOT, 'data', f'{ANO}-{t}')


def dump(t, path, obj):
    p = os.path.join(out_dir(t), path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))


def cand_status(t, sq):
    return SIT[t].get(sq, SIT[1].get(sq, 'N'))


def gov_summary(votes, validos):
    if not votes or not validos or votes[0][1] == 0:
        return None
    second = votes[1][1] if len(votes) > 1 else 0
    return [META[votes[0][0]][2], round((votes[0][1] - second) / validos, 4), votes[0][0]]


def prev_summary(t):
    if not PREV:
        return {}
    p = os.path.join(ROOT, 'data', f'{PREV}-{t}', 'summary.json')
    return json.load(open(p))['el'] if os.path.exists(p) else {}


def build_turn(t):
    print(f'== {ANO} {t}º turno', flush=True)
    V, T = VOTES[t], TOT[t]
    cargos = sorted(c for c in V if c in (1, 3, 5, 6, 7, 8))
    prev = prev_summary(t)
    summary = {}

    def detail(key, uf):
        c = {}
        for cg in cargos:
            vs = sorted(([sq, v] for sq, v in V[cg].get(key, {}).items() if v > 0), key=lambda r: -r[1])
            tt = T.get(cg, {}).get(key)
            if not vs or not tt:
                continue
            c[str(cg)] = {'t': tt, 'v': vs}
        return c

    def put(key, name, uf, c, extra=None):
        c1 = c.get('1')
        if not c1:
            return
        d = dict(c1['v'])
        g = None
        if '3' in c:
            g = gov_summary(c['3']['v'], c['3']['t'][2])
        p = prev.get(key, {})
        summary[key] = {'n': name, 'uf': uf, 't26': c1['t'], 't22': p.get('t26'),
                        'p26': [d.get(PT_SQ, 0), d.get(RIGHT_SQ, 0)], 'p22': p.get('p26'), 'g': g}
        if extra:
            summary[key].update(extra)

    # Brasil e listas da visão país
    br = {'1': {'t': T[1]['br'], 'v': sorted(([sq, v] for sq, v in V[1]['br'].items() if v > 0), key=lambda r: -r[1])}}
    for cg in [c for c in (3, 5, 6) if c in V]:
        lst = []
        for uf in UFS:
            tt = T.get(cg, {}).get(uf)
            if not tt:
                continue
            base = tt[2] + tt[5]
            for sq, v in V[cg].get(uf, {}).items():
                st = cand_status(t, sq)
                if v > 0 and (st in ('E', '2') or t == 2):
                    lst.append([sq, v, round(100 * v / base, 2) if base else 0, uf])
        lst.sort(key=lambda r: -r[2])
        if lst:
            br[str(cg)] = {'v': lst, 'list': True}
    dump(t, 'd/br.json', {'c': br})
    put('br', 'Brasil', 'br', {'1': br['1']})

    for uf in UFS + ['zz']:
        c = detail(uf, uf)
        put(uf, UF_NAMES[uf], uf, c)
        dump(t, f'd/{uf}.json', {'c': c})
    for mun, info in MUNS.items():
        c = detail(mun, info['uf'])
        if not c:
            continue
        put(mun, info['n'], info['uf'], c, {'ibge': info['ibge']})
        dump(t, f'd/{mun}.json', {'c': c})
    zones = sorted(k for k in T[1] if k.startswith('z') and k != 'zz')
    for z in zones:
        uf = z[1:3]
        c = detail(z, uf)
        if not c:
            continue
        muns = sorted(ZONE_MUNS.get(z, ()), key=lambda m: -T[1].get(m, [0])[0])
        put(z, f'Zona {int(z[3:])}', uf, c, {'muns': muns})
        dump(t, f'd/{z}.json', {'c': c})

    # candidatos (situação deste turno)
    cands = defaultdict(dict)
    for sq, m in META.items():
        if any(sq in V[cg].get('br' if m[4] == 1 else m[7], {}) for cg in cargos):
            cands[m[7]][sq] = [m[0], m[1], m[2], cand_status(t, sq), m[4], m[5], m[6]]
    for scope, d in cands.items():
        dump(t, f'cand/{scope}.json', d)
    dump(t, 'summary.json', {'el': summary, 'uf': {u: UF_NAMES[u] for u in UFS + ['zz']}, 'pt': PT_SQ, 'pl': RIGHT_SQ,
                             'meta': {'ano': int(ANO), 'turno': t, 'prev': f'{PREV}-{t}' if PREV else None,
                                      'right': RIGHT[1], 'rightNum': RIGHT[0]}})
    print('  resumo', len(summary), flush=True)


for turno in (1, 2):
    build_turn(turno)


# ------------------------------------------------------------- seções e locais de votação
def load_locais():
    loc, zz = {}, {}
    zn = f'eleitorado_local_votacao_{ANO}.zip'
    z = zipfile.ZipFile(os.path.join(RAW, 'csv', zn))
    for mem in z.namelist():
        if not mem.endswith('.csv') or 'BRASIL' in mem:
            continue
        for r in rows(zn, mem):
            if r.get('NR_TURNO', '1') != '1':
                continue
            uf = r['SG_UF'].lower()
            k = (uf, r['CD_MUNICIPIO'].zfill(5), n(r['NR_ZONA']), n(r['NR_SECAO']))
            if uf == 'zz':
                zz[k] = (r['NM_LOCAL_VOTACAO'], r.get('DS_ENDERECO', ''))
                continue
            try:
                lat = float(r['NR_LATITUDE'].replace(',', '.'))
                lon = float(r['NR_LONGITUDE'].replace(',', '.'))
            except (ValueError, KeyError):
                lat = lon = None
            if lat is not None and (lat == -1 or not (-34 < lat < 6) or not (-75 < lon < -28)):
                lat = lon = None
            loc[k] = (lat, lon, r['NM_LOCAL_VOTACAO'], r.get('NM_BAIRRO', ''))
    return loc, zz


LOC, ZZ_LOC = cached('locais', load_locais)
print('locais com coordenada', sum(1 for v in LOC.values() if v[0] is not None), 'de', len(LOC), flush=True)


def load_secoes():
    """sec_t[turno][(uf, mun, zona, seção)][cargo] = [aptos, comp, válidos, brancos, nulos]
    sec_v[turno][(uf, mun, zona, seção)][cargo][número] = votos (cargos 1, 3, 5)"""
    sec_t = {1: defaultdict(dict), 2: defaultdict(dict)}
    zn = f'detalhe_votacao_secao_{ANO}.zip'
    for mem in members(zn, UFS + ['br', 'zz']):
        for r in rows(zn, mem):
            t = n(r['NR_TURNO'])
            cg = n(r['CD_CARGO'])
            if t not in (1, 2) or cg not in (1, 3, 5):
                continue
            k = (r['SG_UF'].lower(), r['CD_MUNICIPIO'].zfill(5), n(r['NR_ZONA']), n(r['NR_SECAO']))
            sec_t[t][k][cg] = [n(r['QT_APTOS']), n(r['QT_COMPARECIMENTO']),
                               n(r['QT_VOTOS_NOMINAIS']) + n(r['QT_VOTOS_LEGENDA']),
                               n(r['QT_VOTOS_BRANCOS']), n(r['QT_VOTOS_NULOS'])]
        print('  detalhe seção', mem, flush=True)
    sec_v = {1: defaultdict(lambda: defaultdict(dict)), 2: defaultdict(lambda: defaultdict(dict))}
    files = [(f'votacao_secao_{ANO}_BR.zip', f'votacao_secao_{ANO}_BR.csv', ('1',))]
    files += [(f'votacao_secao_{ANO}_{u.upper()}.zip', f'votacao_secao_{ANO}_{u.upper()}.csv', ('3', '5')) for u in UFS]
    for zn, mem, cgs in files:
        for r in rows(zn, mem):
            t = n(r['NR_TURNO'])
            if t not in (1, 2) or r['CD_CARGO'] not in cgs:
                continue
            k = (r['SG_UF'].lower(), r['CD_MUNICIPIO'].zfill(5), n(r['NR_ZONA']), n(r['NR_SECAO']))
            sec_v[t][k][n(r['CD_CARGO'])][r['NR_VOTAVEL']] = n(r['QT_VOTOS'])
        print('  votos seção', mem, flush=True)
    return ({t: dict(sec_t[t]) for t in (1, 2)},
            {t: {k: {c: dict(v) for c, v in d.items()} for k, d in sec_v[t].items()} for t in (1, 2)})


SEC_T, SEC_V = cached('secoes', load_secoes)


def mun_topo_arcs():
    topo = json.load(open(os.path.join(RAW, 'raw', 'mun_int.topo.json')))
    sx, sy = topo['transform']['scale']
    tx, ty = topo['transform']['translate']
    arcs = []
    for arc in topo['arcs']:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return topo, arcs


def mun_centroids():
    topo, arcs = mun_topo_arcs()
    out = {}
    for g in list(topo['objects'].values())[0]['geometries']:
        polys = g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']]
        xs = ys = cnt = 0
        for poly in polys:
            for a in poly[0]:
                for x, y in arcs[a if a >= 0 else ~a]:
                    xs += x
                    ys += y
                    cnt += 1
        if cnt:
            out[g['properties']['codarea']] = (ys / cnt, xs / cnt)
    return out


def build_zone_geometry():
    """mesma técnica do build de 2026: Voronoi dos locais de votação de cada município (cada local
    vai para a zona com mais seções nele), recortado pelo município e unido por zona"""
    import shapely
    import topojson as tp
    from shapely.geometry import MultiPoint, MultiPolygon, Point, Polygon, mapping
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union
    topo, arcs = mun_topo_arcs()

    def ring(idx):
        out = []
        for a in idx:
            pts = arcs[a] if a >= 0 else arcs[~a][::-1]
            out.extend(pts if not out else pts[1:])
        return out

    ibge2tse = {v['ibge']: k for k, v in MUNS.items()}
    mun_poly = {}
    for g in list(topo['objects'].values())[0]['geometries']:
        polys = g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']]
        tse = ibge2tse.get(g['properties']['codarea'])
        if tse:
            mun_poly[tse] = MultiPolygon([Polygon(ring(p[0]), [ring(h) for h in p[1:]]) for p in polys]).buffer(0)
    mun_zones = defaultdict(Counter)
    places = defaultdict(lambda: defaultdict(Counter))
    for (uf, mun, z, s) in SEC_T[1]:
        if uf == 'zz':
            continue
        mun_zones[mun][zid(uf, z)] += 1
        lat, lon = LOC.get((uf, mun, z, s), (None, None, '', ''))[:2]
        if lat is not None:
            places[mun][(round(lon, 5), round(lat, 5))][zid(uf, z)] += 1
    pieces = defaultdict(list)
    for mun, zc in mun_zones.items():
        poly = mun_poly.get(mun)
        if poly is None:
            continue
        if len(zc) == 1:
            pieces[next(iter(zc))].append(poly)
            continue
        near = poly.buffer(0.02)
        pts, lab = [], []
        for (x, y), cnt in places[mun].items():
            if near.contains(Point(x, y)):
                pts.append((x, y))
                lab.append(cnt.most_common(1)[0][0])
        if len(set(lab)) < 2:
            pieces[zc.most_common(1)[0][0]].append(poly)
            continue
        cells = shapely.voronoi_polygons(MultiPoint(pts), extend_to=poly.envelope.buffer(0.2), ordered=True)
        by_zone = defaultdict(list)
        for cell, z in zip(cells.geoms, lab):
            by_zone[z].append(cell)
        for z, cs in by_zone.items():
            part = unary_union(cs).intersection(poly)
            if not part.is_empty:
                pieces[z].append(part)
    feats = []
    for z, ps in pieces.items():
        geom = unary_union(ps)
        geom = geom if geom.geom_type in ('Polygon', 'MultiPolygon') else MultiPolygon(
            [g for g in getattr(geom, 'geoms', []) if g.geom_type == 'Polygon'])
        geom = MultiPolygon([orient(g, sign=-1.0) for g in getattr(geom, 'geoms', [geom])])
        feats.append({'type': 'Feature', 'properties': {'id': z}, 'geometry': mapping(geom)})
    topo_z = tp.Topology({'type': 'FeatureCollection', 'features': feats}, prequantize=1_000_000,
                         toposimplify=0.0004, topology=True).to_dict()
    for t in (1, 2):
        os.makedirs(os.path.join(out_dir(t), 'geo'), exist_ok=True)
        with open(os.path.join(out_dir(t), 'geo', 'zonas.json'), 'w') as f:
            json.dump(topo_z, f, separators=(',', ':'))
    print('  geometria zonas', len(feats), flush=True)


def dist_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def same_building(loc, max_m):
    """{(mun, lat5, lon5): (lat, lon) canônica} para locais de mesmo nome no mesmo município a até
    max_m metros (None = sem limite), usando a coordenada com mais seções"""
    by_name = defaultdict(Counter)
    for k, v in loc.items():
        by_name[(k[1], norm(v[2]))][(round(v[0], 5), round(v[1], 5))] += 1
    canon = {}
    for (mun, _), cnt in by_name.items():
        if len(cnt) < 2:
            continue
        centers = []
        for c, _n in cnt.most_common():
            tgt = next((x for x in centers if max_m is None or dist_m(c, x) <= max_m), None)
            if tgt is None:
                centers.append(c)
            else:
                canon[(mun, c[0], c[1])] = tgt
    return canon


def exterior_coords():
    """(cidade, nome normalizado) e (cidade, endereço normalizado) -> coordenada, a partir das
    coordenadas geocodificadas para 2026; e ponto médio de cada cidade como último recurso"""
    coords = json.load(open(os.path.join(TOOLS, 'exterior_coords.json')))
    by_name, by_addr, city = {}, {}, defaultdict(list)
    for r in rows('eleitorado_local_votacao_2026.zip', 'eleitorado_local_votacao_2026_ZZ.csv'):
        if r['NR_TURNO'] != '1':
            continue
        cd = r['CD_MUNICIPIO'].zfill(5)
        c = coords.get(f"{cd}-{r['NR_LOCAL_VOTACAO']}")
        if not c:
            continue
        by_name.setdefault((cd, norm(r['NM_LOCAL_VOTACAO'])), c)
        by_addr.setdefault((cd, norm(r['DS_ENDERECO'])), c)
        city[cd].append(c)
    city_c = {cd: (sum(c[0] for c in cs) / len(cs), sum(c[1] for c in cs) / len(cs)) for cd, cs in city.items()}
    return by_name, by_addr, city_c


def build_sections(t):
    rnd = random.Random(1)
    cent = mun_centroids()
    st, sv = SEC_T[t], SEC_V[t]
    cg_list = (1, 3, 5) if t == 1 else (1, 3)
    num_meta = {}   # (escopo, cargo, número) -> metadados
    for sq, m in META.items():
        num_meta[(m[7], m[4], m[1])] = m
    sj_nums = defaultdict(set)
    gov_party = defaultdict(dict)
    for sq, m in META.items():
        if cand_status(t, sq) == 'A':
            sj_nums[(m[7], m[4])].add(m[1])
        if m[4] == 3:
            gov_party[m[7]][m[1]] = m[2]
    canon = same_building({k: v for k, v in LOC.items() if v[0] is not None}, max_m=300)
    groups = defaultdict(lambda: defaultdict(list))
    meta = {}
    for k in st:
        uf, mun, z, s = k
        if uf == 'zz':
            continue
        lat, lon, lname, bairro = LOC.get(k, (None, None, '', ''))
        if lat is not None:
            lat, lon = canon.get((mun, round(lat, 5), round(lon, 5)), (lat, lon))
            key = (mun, round(lat, 5), round(lon, 5))
        else:
            key = (mun, None, lname)
        groups[uf][key].append(k)
        meta.setdefault((uf, key), (lat, lon, f'{lname} ({bairro})' if bairro else lname))

    def totals(secs, uf):
        tot = {cg: [0] * 5 for cg in cg_list}
        votes = {cg: defaultdict(int) for cg in cg_list}
        for k in secs:
            for cg in cg_list:
                tt = st[k].get(cg)
                if tt:
                    for i in range(5):
                        tot[cg][i] += tt[i]
                for num, vv in sv.get(k, {}).get(cg, {}).items():
                    if num not in ('95', '96', '97'):
                        votes[cg][num] += vv
        for cg in cg_list:
            sjn = sj_nums.get(('br' if cg == 1 else uf, cg), ())
            sj = sum(v for num, v in votes[cg].items() if num in sjn)
            tot[cg] = tot[cg][:2] + [tot[cg][2] - sj] + tot[cg][3:5] + [sj]
        return tot, votes

    total = 0
    for uf in UFS:
        cols = {c: [] for c in ('m', 'lat', 'lon', 'ns', 'z', 'apt', 'comp', 'val', 'bra', 'nul', 'pt', 'pl', 'gp', 'gm')}
        names, munl, mun_idx, parties, party_idx = [], [], {}, [], {}
        details = defaultdict(dict)
        for key in sorted(groups[uf], key=lambda x: (x[0], str(x[1]), str(x[2]))):
            secs = sorted(groups[uf][key], key=lambda k: (k[2], k[3]))
            mun = key[0]
            lat, lon, name = meta[(uf, key)]
            if lat is None:
                c = cent.get(MUNS.get(mun, {}).get('ibge'))
                if c is None:
                    continue
                lat, lon = c[0] + rnd.uniform(-0.01, 0.01), c[1] + rnd.uniform(-0.01, 0.01)
            tot, votes = totals(secs, uf)
            t1 = tot[1] if tot[1][0] else tot.get(3, [0] * 6)
            gp, gm = -1, 0
            if 3 in tot and tot[3][2]:
                gs = sorted(((vv, num) for num, vv in votes[3].items() if num in gov_party[uf]), reverse=True)
                if gs and gs[0][0] > 0:
                    p = gov_party[uf][gs[0][1]]
                    if p not in party_idx:
                        party_idx[p] = len(parties)
                        parties.append(p)
                    gp = party_idx[p]
                    gm = round(1000 * (gs[0][0] - (gs[1][0] if len(gs) > 1 else 0)) / tot[3][2])
            if mun not in mun_idx:
                mun_idx[mun] = len(munl)
                munl.append(mun)
            i = len(names)
            names.append(name)
            row = {'m': mun_idx[mun], 'lat': round(lat * 1e5), 'lon': round(lon * 1e5), 'ns': len(secs),
                   'z': Counter(k[2] for k in secs).most_common(1)[0][0],
                   'apt': t1[0], 'comp': t1[1], 'val': t1[2], 'bra': t1[3], 'nul': t1[4],
                   'pt': votes[1].get(PT_NUM, 0), 'pl': votes[1].get(RIGHT[0], 0), 'gp': gp, 'gm': gm}
            for c_, val in row.items():
                cols[c_].append(val)
            details[mun][str(i)] = {
                's': [[k[2], k[3]] for k in secs],
                'c': {str(cg): [tot[cg], {n_: v for n_, v in votes[cg].items() if v}] for cg in cg_list if tot[cg][0]},
            }
        cols['names'] = names
        cols['muns'] = munl
        cols['parties'] = parties
        dump(t, f's/{uf}.json', cols)
        for mun, d in details.items():
            dump(t, f'sd/{mun}.json', d)
        total += len(names)
    print('  locais (pontos)', total, flush=True)

    # exterior: casa cada local com as coordenadas geocodificadas em 2026 (nome ou endereço na
    # mesma cidade); sem correspondência, usa o ponto médio da cidade (posição aproximada)
    by_name, by_addr, city_c = exterior_coords()
    pts = defaultdict(lambda: {'secs': [], 'names': set(), 'cities': set(), 'aprox': False})
    sem = 0
    for k in st:
        if k[0] != 'zz':
            continue
        name, addr = ZZ_LOC.get(k, ('', ''))
        c = by_name.get((k[1], norm(name))) or by_addr.get((k[1], norm(addr)))
        aprox = False
        if c:
            lat, lon, aprox = c[0], c[1], c[2].startswith('cidade')
        elif k[1] in city_c:
            (lat, lon), aprox = city_c[k[1]], True
        else:
            sem += 1
            continue
        g = pts[(round(lat, 5), round(lon, 5))]
        g['secs'].append(k)
        g['names'].add(name)
        g['cities'].add(k[1])
        g['aprox'] = g['aprox'] or aprox
    out = []
    for (lat, lon), g in pts.items():
        tt = [0] * 5
        v = defaultdict(int)
        for k in g['secs']:
            x = st[k].get(1)
            if x:
                for i in range(5):
                    tt[i] += x[i]
            for num, vv in sv.get(k, {}).get(1, {}).items():
                if num not in ('95', '96', '97') and vv:
                    v[num] += vv
        if not tt[0]:
            continue
        names = sorted(g['names'])
        out.append({'lat': lat, 'lon': lon, 'n': names[0] if len(names) == 1 else f'{len(names)} locais',
                    'city': ', '.join(sorted(ZZ_NAMES.get(c_, c_) for c_ in g['cities'])), 'ns': len(g['secs']),
                    't': tt, 'v': dict(v), 'aprox': g['aprox'], 's': sorted([k[2], k[3]] for k in g['secs'])})
    out.sort(key=lambda r: -r['t'][0])
    dump(t, 's/zz.json', out)
    print('  pontos no exterior', len(out), '| seções sem coordenada', sem, flush=True)


build_zone_geometry()
for turno in (1, 2):
    build_sections(turno)
print('fim')
