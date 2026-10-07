#!/usr/bin/env python3
"""Gera os arquivos de dados do app (pasta data/) a partir dos arquivos brutos do TSE/IBGE.

Uso: python3 tools/build.py <pasta_bruta>

A pasta bruta deve conter:
  api/   arquivos *-u.json da API de resultados (br, cada UF, zz) para 2026
  raw/   mun-e006257-cm.json, uf_int.topo.json, mun_int.topo.json (IBGE)
  csv/   zips do Portal de Dados Abertos do TSE:
         votacao_candidato_munzona_2026.zip, votacao_secao_2026_BR.zip,
         votacao_secao_2026_<UF>.zip, detalhe_votacao_secao_2026.zip,
         eleitorado_local_votacao_2026.zip,
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
    t = [n(e['te']), n(e['c']), n(v['vv']), n(v['vb']), n(v['tvn'])]
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
def load_munzona():
    """mun -> cargo -> sq -> votos (cargos estaduais)"""
    mv = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    party = {}
    for uf in UFS:
        for r in rows('votacao_candidato_munzona_2026.zip', f'votacao_candidato_munzona_2026_{uf.upper()}.csv'):
            if r['NR_TURNO'] != '1':
                continue
            mun = r['CD_MUNICIPIO'].zfill(5)
            mv[mun][int(r['CD_CARGO'])][r['SQ_CANDIDATO']] += n(r['QT_VOTOS_NOMINAIS'])
            party[r['SQ_CANDIDATO']] = r['SG_PARTIDO']
        print('  munzona', uf)
    return {m: {c: dict(v) for c, v in d.items()} for m, d in mv.items()}, party


MUN_V, CSV_PARTY = cached('munzona', load_munzona)

# Presidente por município: soma das seções
MUN_PRES = defaultdict(lambda: defaultdict(int))
MUN_T = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0, 0]))
for (uf, mun, z, s), d in SEC_V.items():
    if 1 in d:
        for num, v in d[1].items():
            MUN_PRES[mun][num] += v
for (uf, mun, z, s), d in SEC_T.items():
    for cg, t in d.items():
        acc = MUN_T[mun][cg]
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
        for k in (key, uf, 'br') if uf != 'zz' else ('zz', 'br'):
            for i in range(5):
                t[k][i] += vals[i]
    p = defaultdict(lambda: [0, 0])
    for r in rows('votacao_partido_munzona_2022.zip', 'votacao_partido_munzona_2022_BR.csv'):
        if r['NR_TURNO'] != '1' or r['CD_CARGO'] != '1' or r['NR_PARTIDO'] not in ('13', '22'):
            continue
        uf = r['SG_UF'].lower()
        key = 'zz' if uf == 'zz' else r['CD_MUNICIPIO'].zfill(5)
        i = 0 if r['NR_PARTIDO'] == '13' else 1
        for k in (key, uf, 'br') if uf != 'zz' else ('zz', 'br'):
            p[k][i] += n(r['QT_VOTOS_NOMINAIS_VALIDOS'])
    return dict(t), dict(p)


T22, P22 = cached('ano2022', load_2022)


# ------------------------------------------------------ helpers de governador
def gov_summary(votes, validos, party_of):
    """votes: [[sq, votos]] ordenado. -> [partido, margem (fração dos válidos), sq]"""
    if not votes or not validos or votes[0][1] == 0:
        return None
    second = votes[1][1] if len(votes) > 1 else 0
    return [party_of(votes[0][0]), round((votes[0][1] - second) / validos, 4), votes[0][0]]


def cand_party(scope):
    return lambda sq: cands[scope][sq][2] if sq in cands.get(scope, {}) else CSV_PARTY.get(sq, '?')


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
                lst.append([sq, v, round(100 * v / d['t'][2], 2) if d['t'][2] else 0, uf])
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
    c[1] = {'t': MUN_T[mun][1], 'v': pv}
    for cg in cargos_uf(uf):
        votes = MUN_V.get(mun, {}).get(cg, {})
        c[cg] = {'t': MUN_T[mun][cg], 'v': sorted([[sq, v] for sq, v in votes.items() if v > 0], key=lambda r: -r[1]),
                 'nv': uf_detail[uf][cg]['nv']}
    gov = gov_summary(c[3]['v'], c[3]['t'][2], cand_party(uf))
    put(mun, info['n'], uf, c[1], gov)
    summary[mun]['ibge'] = info['ibge']
    dump(f'd/{mun}.json', {'c': {str(k): v for k, v in c.items()}})

for scope, d in cands.items():
    dump(f'cand/{scope}.json', d)

dump('summary.json', {'el': summary, 'uf': {u: UF_NAMES[u] for u in UFS + ['zz']},
                      'pt': PT_SQ, 'pl': PL_SQ})
print('resumo ok', len(summary))

# ------------------------------------------------------------ seções
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


LOC = cached('locais', load_locais)
print('locais', len(LOC))

# centróides de fallback via IBGE (topojson): média dos vértices do arco
def mun_centroids():
    topo = json.load(open(os.path.join(RAW, 'raw', 'mun_int.topo.json')))
    tr = topo['transform']
    sx, sy = tr['scale']
    tx, ty = tr['translate']
    arcs = []
    for arc in topo['arcs']:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    obj = list(topo['objects'].values())[0]
    out = {}
    for g in obj['geometries']:
        polys = g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']]
        xs = ys = cnt = 0
        for poly in polys:
            for ring in poly[:1]:
                for a in ring:
                    for x, y in arcs[a if a >= 0 else ~a]:
                        xs += x
                        ys += y
                        cnt += 1
        if cnt:
            out[g['properties']['codarea']] = (ys / cnt, xs / cnt)
    return out


CENT = mun_centroids()

# índices de candidatos por número para governador (por UF)
GOV_NUM = {uf: {v[1]: (sq, v[2]) for sq, v in cands[uf].items() if v[4] == 3} for uf in UFS}

by_uf = defaultdict(list)
for k in SEC_T:
    if k[0] != 'zz':
        by_uf[k[0]].append(k)

import random
random.seed(1)
for uf in UFS:
    keys = sorted(by_uf[uf])
    cols = {k: [] for k in ('m', 'z', 's', 'lat', 'lon', 'l', 'apt', 'comp', 'val', 'bra', 'nul',
                            'pt', 'pl', 'gp', 'gm')}
    locs, loc_idx, munl, mun_idx, parties, party_idx = [], {}, [], {}, [], {}
    details = defaultdict(dict)
    for k in keys:
        _, mun, z, s = k
        t = SEC_T[k].get(1) or SEC_T[k].get(3)
        if t is None:
            continue
        v = SEC_V.get(k, {})
        lat, lon, lname, bairro = LOC.get(k, (None, None, '', ''))
        if lat is None:
            c = CENT.get(MUNS.get(mun, {}).get('ibge'))
            if c is None:
                continue
            lat = c[0] + random.uniform(-0.01, 0.01)
            lon = c[1] + random.uniform(-0.01, 0.01)
        lk = (mun, lname, bairro)
        if lk not in loc_idx:
            loc_idx[lk] = len(locs)
            locs.append(f'{lname} ({bairro})' if bairro else lname)
        if mun not in mun_idx:
            mun_idx[mun] = len(munl)
            munl.append(mun)
        pres = v.get(1, {})
        gov = v.get(3, {})
        gsorted = sorted([(vv, num) for num, vv in gov.items() if num in GOV_NUM[uf]], reverse=True)
        gt = SEC_T[k].get(3, [0, 0, 0, 0, 0])
        if gsorted and gsorted[0][0] > 0 and gt[2]:
            p = GOV_NUM[uf][gsorted[0][1]][1]
            if p not in party_idx:
                party_idx[p] = len(parties)
                parties.append(p)
            gp = party_idx[p]
            gm = round(1000 * (gsorted[0][0] - (gsorted[1][0] if len(gsorted) > 1 else 0)) / gt[2])
        else:
            gp, gm = -1, 0
        row = {'m': mun_idx[mun], 'z': z, 's': s, 'lat': round(lat * 1e4), 'lon': round(lon * 1e4),
               'l': loc_idx[lk], 'apt': t[0], 'comp': t[1], 'val': t[2], 'bra': t[3], 'nul': t[4],
               'pt': pres.get('13', 0), 'pl': pres.get('22', 0), 'gp': gp, 'gm': gm}
        for c_, val in row.items():
            cols[c_].append(val)
        # {cargo: [totais, {número: votos}]}; brancos/nulos (95/96/97) já estão nos totais
        details[mun][f'{z}-{s}'] = {
            str(cg): [SEC_T[k][cg], {num: vv for num, vv in v.get(cg, {}).items() if vv and num not in ('95', '96', '97')}]
            for cg in (1, 3, 5) if SEC_T[k].get(cg)}
    cols['locs'] = locs
    cols['muns'] = munl
    cols['parties'] = parties
    dump(f's/{uf}.json', cols)
    for mun, d in details.items():
        dump(f'sd/{mun}.json', d)
    print('  secoes', uf, len(cols['s']))

print('fim')
