#!/usr/bin/env python3
"""Gera os arquivos de dados do app (pasta data/) a partir dos arquivos brutos do TSE/IBGE.

Uso: python3 tools/build.py <pasta_bruta>

A pasta bruta deve conter:
  api/   arquivos *-u.json da API de resultados (br, cada UF, zz) para 2026
  raw/   mun-e006257-cm.json, uf_int.topo.json, mun_int.topo.json (IBGE)
  csv/   zips do Portal de Dados Abertos do TSE:
         votacao_candidato_munzona_2026.zip, votacao_secao_2026_BR.zip,
         votacao_secao_2026_<UF>.zip, detalhe_votacao_secao_2026.zip,
         eleitorado_local_votacao_2026.zip (coordenadas dos locais, para as áreas das zonas),
         detalhe_votacao_munzona_2022.zip, votacao_partido_munzona_2022.zip
"""
import csv
import io
import json
import os
import pickle
import sys
import zipfile
from collections import defaultdict

RAW = sys.argv[1]
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
OUT = os.path.join(ROOT, 'data')
CACHE = os.path.join(RAW, 'cache')
os.makedirs(CACHE, exist_ok=True)

UFS = ['ac', 'al', 'ap', 'am', 'ba', 'ce', 'df', 'es', 'go', 'ma', 'mt', 'ms', 'mg', 'pa',
       'pb', 'pr', 'pe', 'pi', 'rj', 'rn', 'rs', 'ro', 'rr', 'sc', 'se', 'sp', 'to']
UF_NAMES = {}
csv.field_size_limit(10**9)


def cargos_uf(uf):
    return [3, 5, 6, 8] if uf == 'df' else [3, 5, 6, 7]


def n(x):
    return int(x) if x not in ('', None) else 0


def dump(path, obj):
    path = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))


def cached(name, fn):
    p = os.path.join(CACHE, name + '.pkl')
    if os.path.exists(p):
        with open(p, 'rb') as f:
            return pickle.load(f)
    v = fn()
    with open(p, 'wb') as f:
        pickle.dump(v, f)
    return v


def rows(zipname, member):
    z = zipfile.ZipFile(os.path.join(RAW, 'csv', zipname))
    with z.open(member) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, 'latin1'), delimiter=';')


def api(uf, cargo, mun=''):
    ele = 6257 if cargo == 1 else 6259
    p = os.path.join(RAW, 'api', f'{uf}{mun}-c{cargo:04d}-e{ele:06d}-u.json')
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def status(c):
    if 'anulado' in c.get('dvt', '').lower():
        return 'A'
    st = c['st'].lower()
    if st.startswith('eleito'):
        return 'E'
    if '2' in st and 'turno' in st:
        return '2'
    if st.startswith('suplente'):
        return 'S'
    return 'N'


# ---------------------------------------------------------------- municípios
cm = json.load(open(os.path.join(RAW, 'raw', 'mun-e006257-cm.json'), encoding='utf-8'))
MUNS = {}       # tse code -> dict(n, uf, ibge)
for a in cm['abr']:
    UF_NAMES[a['cd']] = a['ds'].title().replace(' Do ', ' do ').replace(' De ', ' de ').replace(' Da ', ' da ')
    if a['cd'] == 'zz':
        continue
    for m in a['mu']:
        MUNS[m['cd']] = {'n': m['nm'], 'uf': a['cd'], 'ibge': m['cdi']}
UF_NAMES['df'] = 'Distrito Federal'
UF_NAMES['zz'] = 'Exterior'
print('municipios', len(MUNS))

# ------------------------------------------------- candidatos (API por UF)
cands = {}      # scope -> {sq: [nome urna, numero, partido, status, cargo, nome completo]}
uf_detail = {}  # uf -> {cargo: {'t':..., 'v': [[sq, votos]]}}


def parse_api(d, scope, store_cands=True):
    c = d['carg'][0]
    cargo = int(c['cd'])
    out = []
    for a in c['agr']:
        for p in a['par']:
            for x in p['cand']:
                if store_cands:
                    cands.setdefault(scope, {})[x['sqcand']] = [
                        x['nmu'], x['n'], p['sg'], status(x), cargo, x['nm'], a.get('com', p['sg'])]
                out.append([x['sqcand'], n(x['vap'])])
    out.sort(key=lambda r: -r[1])
    e, v = d['e'], d['v']
    # [aptos, comparecimento, válidos, brancos, nulos, anulados sub judice]
    t = [n(e['te']), n(e['c']), n(v['vv']), n(v['vb']), n(v['tvn']), n(v.get('vansj', 0))]
    return cargo, {'t': t, 'v': out, 'nv': n(c.get('nv', 0))}


br_pres = api('br', 1)
_, br_c1 = parse_api(br_pres, 'br')
for uf in UFS + ['zz']:
    uf_detail[uf] = {}
    _, uf_detail[uf][1] = parse_api(api(uf, 1), 'br', store_cands=False)
    if uf == 'zz':
        continue
    for cg in cargos_uf(uf):
        _, uf_detail[uf][cg] = parse_api(api(uf, cg), uf)

# presidente: sq por número
PRES_NUM = {v[1]: sq for sq, v in cands['br'].items()}
PT_SQ = PRES_NUM['13']
PL_SQ = PRES_NUM['22']

# --------------------------------------------- totais por seção (detalhe)
def load_detalhe():
    """(uf, mun, zona, secao) -> {cargo: [aptos, comp, validos, brancos, nulos]}"""
    sec = defaultdict(dict)
    z = zipfile.ZipFile(os.path.join(RAW, 'csv', 'detalhe_votacao_secao_2026.zip'))
    for mem in z.namelist():
        if not mem.endswith('.csv') or 'BRASIL' in mem:
            continue
        for r in rows('detalhe_votacao_secao_2026.zip', mem):
            if r['NR_TURNO'] != '1':
                continue
            k = (r['SG_UF'].lower(), r['CD_MUNICIPIO'].zfill(5), int(r['NR_ZONA']), int(r['NR_SECAO']))
            sec[k][int(r['CD_CARGO'])] = [n(r['QT_APTOS']), n(r['QT_COMPARECIMENTO']),
                                          n(r['QT_VOTOS_NOMINAIS']) + n(r['QT_VOTOS_LEGENDA']),
                                          n(r['QT_VOTOS_BRANCOS']), n(r['QT_VOTOS_NULOS'])]
    return dict(sec)


SEC_T = cached('detalhe_secao', load_detalhe)
print('secoes', len(SEC_T))


# ------------------------------------------- votos por seção (pres, gov, sen)
def load_secao_votes():
    """(uf, mun, zona, secao) -> {cargo: {numero: votos}} para cargos 1, 3 e 5"""
    sec = defaultdict(lambda: defaultdict(dict))
    for r in rows('votacao_secao_2026_BR.zip', 'votacao_secao_2026_BR.csv'):
        if r['NR_TURNO'] != '1':
            continue
        k = (r['SG_UF'].lower(), r['CD_MUNICIPIO'].zfill(5), int(r['NR_ZONA']), int(r['NR_SECAO']))
        sec[k][1][r['NR_VOTAVEL']] = n(r['QT_VOTOS'])
    for uf in UFS:
        for r in rows(f'votacao_secao_2026_{uf.upper()}.zip', f'votacao_secao_2026_{uf.upper()}.csv'):
            if r['NR_TURNO'] != '1' or r['CD_CARGO'] not in ('3', '5'):
                continue
            k = (uf, r['CD_MUNICIPIO'].zfill(5), int(r['NR_ZONA']), int(r['NR_SECAO']))
            sec[k][int(r['CD_CARGO'])][r['NR_VOTAVEL']] = n(r['QT_VOTOS'])
        print('  secao votos', uf)
    return {k: {c: dict(v) for c, v in d.items()} for k, d in sec.items()}


SEC_V = cached('secao_votos', load_secao_votes)
print('secoes com votos', len(SEC_V))

# ------------------------------------------------ votos por município (CSV)
def zid(uf, z):
    """id da zona eleitoral (numeração por UF)"""
    return f'z{uf}{int(z):04d}'


def load_munzona():
    """mun -> cargo -> sq -> votos e zona -> cargo -> sq -> votos (cargos estaduais)"""
    mv = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    zv = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    party = {}
    for uf in UFS:
        for r in rows('votacao_candidato_munzona_2026.zip', f'votacao_candidato_munzona_2026_{uf.upper()}.csv'):
            if r['NR_TURNO'] != '1':
                continue
            mun = r['CD_MUNICIPIO'].zfill(5)
            mv[mun][int(r['CD_CARGO'])][r['SQ_CANDIDATO']] += n(r['QT_VOTOS_NOMINAIS'])
            zv[zid(uf, r['NR_ZONA'])][int(r['CD_CARGO'])][r['SQ_CANDIDATO']] += n(r['QT_VOTOS_NOMINAIS'])
            party[r['SQ_CANDIDATO']] = r['SG_PARTIDO']
        print('  munzona', uf)
    flat = lambda x: {m: {c: dict(v) for c, v in d.items()} for m, d in x.items()}
    return flat(mv), party, flat(zv)


MUN_V, CSV_PARTY, ZONE_V = cached('munzona2', load_munzona)

# Presidente e totais por município e por zona: soma das seções
MUN_PRES = defaultdict(lambda: defaultdict(int))
ZONE_PRES = defaultdict(lambda: defaultdict(int))
MUN_T = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0, 0]))
ZONE_T = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0, 0]))
ZONE_MUNS = defaultdict(set)
for (uf, mun, z, s), d in SEC_V.items():
    if 1 in d:
        for num, v in d[1].items():
            MUN_PRES[mun][num] += v
            if uf != 'zz':
                ZONE_PRES[zid(uf, z)][num] += v
for (uf, mun, z, s), d in SEC_T.items():
    if uf != 'zz':
        ZONE_MUNS[zid(uf, z)].add(mun)
    for cg, t in d.items():
        for acc in (MUN_T[mun][cg], ZONE_T[zid(uf, z)][cg] if uf != 'zz' else [0] * 5):
            for i in range(5):
                acc[i] += t[i]

# ------------------------------------------------------------- 2022
def load_2022():
    t = defaultdict(lambda: [0, 0, 0, 0, 0])
    for r in rows('detalhe_votacao_munzona_2022.zip', 'detalhe_votacao_munzona_2022_BR.csv'):
        if r['NR_TURNO'] != '1' or r['CD_CARGO'] != '1':
            continue
        uf = r['SG_UF'].lower()
        key = 'zz' if uf == 'zz' else r['CD_MUNICIPIO'].zfill(5)
        vals = [n(r['QT_APTOS']), n(r['QT_COMPARECIMENTO']), n(r['QT_TOTAL_VOTOS_VALIDOS']),
                n(r['QT_VOTOS_BRANCOS']), n(r['QT_TOTAL_VOTOS_NULOS'])]
        for k in (key, uf, 'br', zid(uf, r['NR_ZONA'])) if uf != 'zz' else ('zz', 'br'):
            for i in range(5):
                t[k][i] += vals[i]
    p = defaultdict(lambda: [0, 0])
    for r in rows('votacao_partido_munzona_2022.zip', 'votacao_partido_munzona_2022_BR.csv'):
        if r['NR_TURNO'] != '1' or r['CD_CARGO'] != '1' or r['NR_PARTIDO'] not in ('13', '22'):
            continue
        uf = r['SG_UF'].lower()
        key = 'zz' if uf == 'zz' else r['CD_MUNICIPIO'].zfill(5)
        i = 0 if r['NR_PARTIDO'] == '13' else 1
        for k in (key, uf, 'br', zid(uf, r['NR_ZONA'])) if uf != 'zz' else ('zz', 'br'):
            p[k][i] += n(r['QT_VOTOS_NOMINAIS_VALIDOS'])
    return dict(t), dict(p)


T22, P22 = cached('ano2022z', load_2022)


# ------------------------------------------------------ helpers de governador
def gov_summary(votes, validos, party_of):
    """votes: [[sq, votos]] ordenado. -> [partido, margem (fração dos válidos), sq]"""
    if not votes or not validos or votes[0][1] == 0:
        return None
    second = votes[1][1] if len(votes) > 1 else 0
    return [party_of(votes[0][0]), round((votes[0][1] - second) / validos, 4), votes[0][0]]


def cand_party(scope):
    return lambda sq: cands[scope][sq][2] if sq in cands.get(scope, {}) else CSV_PARTY.get(sq, '?')


def split_sj(t, votes, scope):
    """Totais vindos do CSV contam os votos anulados sub judice como válidos. Separa-os como
    no TSE: [aptos, comp, válidos, brancos, nulos, anulados sub judice]. votes: [[sq, votos]]."""
    sj = sum(v for sq, v in votes if cands.get(scope, {}).get(sq, [None] * 4)[3] == 'A')
    return [t[0], t[1], t[2] - sj, t[3], t[4], sj]


# ----------------------------------------------------------- saída: resumo
summary = {}


def pres_pt_pl(c1):
    d = dict((sq, v) for sq, v in c1['v'])
    return [d.get(PT_SQ, 0), d.get(PL_SQ, 0)]


def put(el_id, name, uf, c1, gov):
    summary[el_id] = {
        'n': name, 'uf': uf,
        't26': c1['t'],
        't22': T22.get(el_id),
        'p26': pres_pt_pl(c1),
        'p22': P22.get(el_id),
        'g': gov,
    }


put('br', 'Brasil', 'br', br_c1, None)
dump('d/br.json', {'c': {'1': br_c1}})

# país: listas de eleitos/2º turno para governador, senador e dep. federal
for cg in (3, 5, 6):
    lst = []
    for uf in UFS:
        d = uf_detail[uf][cg]
        for sq, v in d['v']:
            stt = cands[uf][sq][3]
            if stt in ('E', '2'):
                base = d['t'][2] + d['t'][5]
                lst.append([sq, v, round(100 * v / base, 2) if base else 0, uf])
    lst.sort(key=lambda r: -r[2])
    br_detail = json.load(open(os.path.join(OUT, 'd/br.json')))
    br_detail['c'][str(cg)] = {'v': lst, 'list': True}
    dump('d/br.json', br_detail)

for uf in UFS + ['zz']:
    det = uf_detail[uf]
    gov = gov_summary(det[3]['v'], det[3]['t'][2], cand_party(uf)) if 3 in det else None
    put(uf, UF_NAMES[uf], uf, det[1], gov)
    dump(f'd/{uf}.json', {'c': {str(k): v for k, v in det.items()}})

for mun, info in MUNS.items():
    uf = info['uf']
    c = {}
    pres = MUN_PRES.get(mun, {})
    pv = sorted([[PRES_NUM[num], v] for num, v in pres.items() if num in PRES_NUM], key=lambda r: -r[1])
    c[1] = {'t': split_sj(MUN_T[mun][1], pv, 'br'), 'v': pv}
    for cg in cargos_uf(uf):
        votes = MUN_V.get(mun, {}).get(cg, {})
        vs = sorted([[sq, v] for sq, v in votes.items() if v > 0], key=lambda r: -r[1])
        c[cg] = {'t': split_sj(MUN_T[mun][cg], vs, uf), 'v': vs,
                 'nv': uf_detail[uf][cg]['nv']}
    gov = gov_summary(c[3]['v'], c[3]['t'][2], cand_party(uf))
    put(mun, info['n'], uf, c[1], gov)
    summary[mun]['ibge'] = info['ibge']
    dump(f'd/{mun}.json', {'c': {str(k): v for k, v in c.items()}})

# ------------------------------------------------------------ zonas eleitorais
for z_id in sorted(ZONE_T):
    uf = z_id[1:3]
    c = {}
    pv = sorted([[PRES_NUM[num], v] for num, v in ZONE_PRES.get(z_id, {}).items() if num in PRES_NUM],
                key=lambda r: -r[1])
    c[1] = {'t': split_sj(ZONE_T[z_id][1], pv, 'br'), 'v': pv}
    for cg in cargos_uf(uf):
        votes = ZONE_V.get(z_id, {}).get(cg, {})
        vs = sorted([[sq, v] for sq, v in votes.items() if v > 0], key=lambda r: -r[1])
        c[cg] = {'t': split_sj(ZONE_T[z_id][cg], vs, uf), 'v': vs,
                 'nv': uf_detail[uf][cg]['nv']}
    gov = gov_summary(c[3]['v'], c[3]['t'][2], cand_party(uf))
    put(z_id, f'Zona {int(z_id[3:])}', uf, c[1], gov)
    summary[z_id]['muns'] = sorted(ZONE_MUNS[z_id], key=lambda m: -MUN_T[m][1][0])
    dump(f'd/{z_id}.json', {'c': {str(k): v for k, v in c.items()}})
print('zonas', len(ZONE_T))


def load_locais():
    loc = {}
    z = zipfile.ZipFile(os.path.join(RAW, 'csv', 'eleitorado_local_votacao_2026.zip'))
    for mem in z.namelist():
        if not mem.endswith('.csv') or 'BRASIL' in mem or mem.endswith('_ZZ.csv'):
            continue
        for r in rows('eleitorado_local_votacao_2026.zip', mem):
            if r['NR_TURNO'] != '1':
                continue
            try:
                lat = float(r['NR_LATITUDE'].replace(',', '.'))
                lon = float(r['NR_LONGITUDE'].replace(',', '.'))
            except ValueError:
                lat = lon = None
            if lat is not None and (lat == -1 or not (-34 < lat < 6) or not (-75 < lon < -28)):
                lat = lon = None
            k = (r['SG_UF'].lower(), r['CD_MUNICIPIO'].zfill(5), int(r['NR_ZONA']), int(r['NR_SECAO']))
            loc[k] = (lat, lon, r['NM_LOCAL_VOTACAO'], r['NM_BAIRRO'])
    return loc


def build_zone_geometry():
    """Área aproximada de cada zona: polígonos de Voronoi dos locais de votação de cada
    município (cada local vai para a zona com mais seções nele), recortados pelo limite
    do município e unidos por zona. Municípios com uma só zona entram inteiros."""
    from collections import Counter
    from shapely.geometry import MultiPoint, Point, Polygon, MultiPolygon, mapping
    from shapely.geometry.polygon import orient
    import shapely
    from shapely.ops import unary_union
    import topojson as tp

    LOC = cached('locais', load_locais)
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
        shp = MultiPolygon([Polygon(ring(p[0]), [ring(h) for h in p[1:]]) for p in polys]).buffer(0)
        tse = ibge2tse.get(g['properties']['codarea'])
        if tse:
            mun_poly[tse] = shp

    # seções por (município, zona) e locais com coordenadas
    mun_zones = defaultdict(Counter)
    places = defaultdict(lambda: defaultdict(Counter))   # mun -> (lon, lat) -> Counter(zona)
    for (uf, mun, z, s) in SEC_T:
        if uf == 'zz':
            continue
        mun_zones[mun][zid(uf, z)] += 1
        lat, lon, _, _ = LOC.get((uf, mun, z, s), (None, None, '', ''))
        if lat is not None:
            places[mun][(round(lon, 5), round(lat, 5))][zid(uf, z)] += 1

    pieces = defaultdict(list)
    sem_geo = 0
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
            # sem como separar: o município inteiro vai para a zona com mais seções
            pieces[zc.most_common(1)[0][0]].append(poly)
            sem_geo += len(zc) - 1
            continue
        cells = shapely.voronoi_polygons(MultiPoint(pts), extend_to=poly.envelope.buffer(0.2), ordered=True)
        by_zone = defaultdict(list)
        for cell, z in zip(cells.geoms, lab):
            by_zone[z].append(cell)
        for z, cs in by_zone.items():
            part = unary_union(cs).intersection(poly)
            if not part.is_empty:
                pieces[z].append(part)
        sem_geo += sum(1 for z in zc if z not in by_zone)
    print('  zonas sem área própria em algum município:', sem_geo)

    feats = []
    for z, ps in pieces.items():
        geom = unary_union(ps)
        geom = geom if geom.geom_type in ('Polygon', 'MultiPolygon') else MultiPolygon(
            [g for g in getattr(geom, 'geoms', []) if g.geom_type == 'Polygon'])
        # d3-geo (esférico) espera o anel externo no sentido horário
        geom = MultiPolygon([orient(g, sign=-1.0) for g in getattr(geom, 'geoms', [geom])])
        feats.append({'type': 'Feature', 'properties': {'id': z}, 'geometry': mapping(geom)})
    fc = {'type': 'FeatureCollection', 'features': feats}
    topo_z = tp.Topology(fc, prequantize=1_000_000, toposimplify=0.0004, topology=True).to_dict()
    # o pacote nomeia o objeto como 'data'
    os.makedirs(os.path.join(OUT, 'geo'), exist_ok=True)
    with open(os.path.join(OUT, 'geo', 'zonas.json'), 'w') as f:
        json.dump(topo_z, f, separators=(',', ':'))
    print('  geometria zonas', len(feats))


build_zone_geometry()


# ------------------------------------------------- seções (agrupadas por local)
# Seções exatamente no mesmo local (mesmas coordenadas) viram um único ponto.
def mun_centroids():
    """centróide aproximado (média dos vértices do anel externo) por código IBGE"""
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


def build_locais():
    import random
    from collections import Counter
    rnd = random.Random(1)
    LOC = cached('locais', load_locais)
    CENT = mun_centroids()
    gov_num = {uf: {v[1]: v[2] for v in cands[uf].values() if v[4] == 3} for uf in UFS}
    sj_nums = defaultdict(set)   # (escopo, cargo) -> números de candidatos com votos anulados sub judice
    for scope, d in cands.items():
        for v in d.values():
            if v[3] == 'A':
                sj_nums[(scope, v[4])].add(v[1])

    groups = defaultdict(lambda: defaultdict(list))   # uf -> chave do local -> [seções]
    meta = {}
    for k in SEC_T:
        uf, mun, z, s = k
        if uf == 'zz':
            continue
        lat, lon, lname, bairro = LOC.get(k, (None, None, '', ''))
        if lat is not None:
            key = (mun, round(lat, 5), round(lon, 5))
        else:
            key = (mun, None, lname)
        groups[uf][key].append(k)
        meta.setdefault((uf, key), (lat, lon, f'{lname} ({bairro})' if bairro else lname))

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
                c = CENT.get(MUNS.get(mun, {}).get('ibge'))
                if c is None:
                    continue
                lat, lon = c[0] + rnd.uniform(-0.01, 0.01), c[1] + rnd.uniform(-0.01, 0.01)
            tot = {cg: [0] * 5 for cg in (1, 3, 5)}
            votes = {cg: defaultdict(int) for cg in (1, 3, 5)}
            for k in secs:
                for cg in (1, 3, 5):
                    t = SEC_T[k].get(cg)
                    if t:
                        for i in range(5):
                            tot[cg][i] += t[i]
                    for num, vv in SEC_V.get(k, {}).get(cg, {}).items():
                        if num not in ('95', '96', '97'):
                            votes[cg][num] += vv
            # separa os anulados sub judice dos válidos (6º campo), como no TSE
            for cg in (1, 3, 5):
                sjn = sj_nums.get(('br' if cg == 1 else uf, cg), ())
                sj = sum(v for num, v in votes[cg].items() if num in sjn)
                tot[cg] = tot[cg][:2] + [tot[cg][2] - sj] + tot[cg][3:5] + [sj]
            t1 = tot[1] if tot[1][0] else tot[3]
            gs = sorted(((vv, num) for num, vv in votes[3].items() if num in gov_num[uf]), reverse=True)
            if gs and gs[0][0] > 0 and tot[3][2]:
                p = gov_num[uf][gs[0][1]]
                if p not in party_idx:
                    party_idx[p] = len(parties)
                    parties.append(p)
                gp = party_idx[p]
                gm = round(1000 * (gs[0][0] - (gs[1][0] if len(gs) > 1 else 0)) / tot[3][2])
            else:
                gp, gm = -1, 0
            if mun not in mun_idx:
                mun_idx[mun] = len(munl)
                munl.append(mun)
            i = len(names)
            names.append(name)
            row = {'m': mun_idx[mun], 'lat': round(lat * 1e5), 'lon': round(lon * 1e5), 'ns': len(secs),
                   'z': Counter(k[2] for k in secs).most_common(1)[0][0],
                   'apt': t1[0], 'comp': t1[1], 'val': t1[2], 'bra': t1[3], 'nul': t1[4],
                   'pt': votes[1].get('13', 0), 'pl': votes[1].get('22', 0), 'gp': gp, 'gm': gm}
            for c_, val in row.items():
                cols[c_].append(val)
            # detalhe: seções [[zona, seção]] e {cargo: [totais, {número: votos}]}
            details[mun][str(i)] = {
                's': [[k[2], k[3]] for k in secs],
                'c': {str(cg): [tot[cg], {n_: v for n_, v in votes[cg].items() if v}] for cg in (1, 3, 5) if tot[cg][0]},
            }
        cols['names'] = names
        cols['muns'] = munl
        cols['parties'] = parties
        dump(f's/{uf}.json', cols)
        for mun, d in details.items():
            dump(f'sd/{mun}.json', d)
        total += len(names)
    print('locais de votação (pontos)', total)

    # exterior: o TSE não publica coordenadas; tools/geocode_exterior.py geocodifica os
    # endereços (Nominatim/OSM) em tools/exterior_coords.json. Locais com a mesma coordenada
    # viram um ponto; sem coordenada, o local fica sem ponto (entra só no total do exterior).
    zz_names = {m['cd']: m['nm'] for a in cm['abr'] if a['cd'] == 'zz' for m in a['mu']}
    cpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exterior_coords.json')
    coords = json.load(open(cpath)) if os.path.exists(cpath) else {}
    zz_loc = {}
    for r in rows('eleitorado_local_votacao_2026.zip', 'eleitorado_local_votacao_2026_ZZ.csv'):
        if r['NR_TURNO'] == '1':
            zz_loc[(r['CD_MUNICIPIO'].zfill(5), int(r['NR_ZONA']), int(r['NR_SECAO']))] = (
                r['NR_LOCAL_VOTACAO'], r['NM_LOCAL_VOTACAO'])
    pts = defaultdict(lambda: {'secs': [], 'names': set(), 'cities': set(), 'src': set()})
    sem = 0
    for k in SEC_T:
        if k[0] != 'zz':
            continue
        nr, name = zz_loc.get((k[1], k[2], k[3]), (None, ''))
        c = coords.get(f'{k[1]}-{nr}')
        if not c:
            sem += 1
            continue
        g = pts[(round(c[0], 5), round(c[1], 5))]
        g['secs'].append(k)
        g['names'].add(name)
        g['cities'].add(k[1])
        g['src'].add(c[2])
    out = []
    for (lat, lon), g in pts.items():
        t = [0] * 5
        v = defaultdict(int)
        for k in g['secs']:
            tt = SEC_T[k].get(1)
            if tt:
                for i in range(5):
                    t[i] += tt[i]
            for num, vv in SEC_V.get(k, {}).get(1, {}).items():
                if num not in ('95', '96', '97') and vv:
                    v[num] += vv
        if not t[0]:
            continue
        names = sorted(g['names'])
        city = ', '.join(sorted(zz_names.get(c_, c_) for c_ in g['cities']))
        out.append({'lat': lat, 'lon': lon, 'n': names[0] if len(names) == 1 else f'{len(names)} locais',
                    'city': city, 'ns': len(g['secs']), 't': t, 'v': dict(v),
                    'aprox': any(x.startswith('cidade') for x in g['src']),
                    's': sorted([k[2], k[3]] for k in g['secs'])})
    out.sort(key=lambda r: -r['t'][0])
    dump('s/zz.json', out)
    print('pontos no exterior', len(out), '| seções sem coordenada', sem)


build_locais()

for scope, d in cands.items():
    dump(f'cand/{scope}.json', d)

dump('summary.json', {'el': summary, 'uf': {u: UF_NAMES[u] for u in UFS + ['zz']},
                      'pt': PT_SQ, 'pl': PL_SQ})
print('resumo ok', len(summary))
