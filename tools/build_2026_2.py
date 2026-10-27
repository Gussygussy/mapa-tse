#!/usr/bin/env python3
"""Gera data/2026-2/ (2º turno de 2026) com o resultado final.

Uso: python3 tools/build_2026_2.py <pasta_api> <detalhe_votacao_secao_2026.zip>

<pasta_api>: arquivos -u.json da API de resultados do TSE (ver tools/baixar_2026_2.py):
  br, cada UF e zz (presidente, eleição 6258), as 6 UFs com 2º turno para governador (6260) e
  cada par município-zona ({uf}{mun}-z{zona}). Município = soma das suas zonas; zona = soma dos
  seus municípios; UF e Brasil = arquivos oficiais da UF e do Brasil (conferidos com a soma).

Seções: os locais de votação (pontos) são os mesmos do 1º turno (data/2026-1/s e sd). O
detalhe por seção dos dados abertos já traz o 2º turno (aptos, comparecimento, brancos, nulos),
mas os votos por candidato em cada seção ainda não foram publicados pelo TSE; até lá os pontos
têm só as métricas de participação.
"""
import csv
import io
import json
import os
import shutil
import sys
import zipfile
from collections import defaultdict

API, DETALHE = sys.argv[1], sys.argv[2]
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
BASE = os.path.join(ROOT, 'data', '2026-1')
OUT = os.path.join(ROOT, 'data', '2026-2')
PRES, GOV = 6258, 6260
GOV_UFS = ['ac', 'am', 'df', 'es', 'rn', 'to']
csv.field_size_limit(10**9)

base = json.load(open(os.path.join(BASE, 'summary.json')))
BEL, UF_NAMES = base['el'], base['uf']
UFS = [u for u in UF_NAMES if u != 'zz']
prev = json.load(open(os.path.join(ROOT, 'data', '2022-2', 'summary.json')))['el']


def dump(path, obj):
    p = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))


def status(c):
    if 'anulado' in (c.get('dvt') or '').lower():
        return 'A'
    st = (c.get('st') or '').lower()
    if st.startswith('eleito'):
        return 'E'
    return 'N'


CANDS = {}   # escopo -> sq -> [urna, número, partido, situação, cargo, nome, coligação]


def api(uf, cargo, suf=''):
    ele = PRES if cargo == 1 else GOV
    p = os.path.join(API, f'{uf}{suf}-c{cargo:04d}-e{ele:06d}-u.json')
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding='utf-8'))
    c = d['carg'][0]
    votes = {}
    scope = 'br' if cargo == 1 else uf
    for a in c.get('agr') or []:
        for par in a.get('par') or []:
            for x in par.get('cand') or []:
                votes[x['sqcand']] = int(x.get('vap') or 0)
                CANDS.setdefault(scope, {})[x['sqcand']] = [x['nmu'], x['n'], par['sg'], status(x), cargo, x['nm'],
                                                            a.get('com') or par['sg']]
    e, v = d.get('e') or {}, d.get('v') or {}
    t = [int(e.get('te') or 0), int(e.get('c') or 0), int(v.get('vv') or 0), int(v.get('vb') or 0),
         int(v.get('tvn') or 0), int(v.get('vansj') or 0)]
    sec = d.get('s') or {}
    return {'t': t, 'v': votes, 'sec': (int(sec.get('st') or 0), int(sec.get('ts') or 0))}


def add(acc, r):
    if not r:
        return
    a = acc.setdefault('t', [0] * 6)
    for i in range(6):
        a[i] += r['t'][i]
    vv = acc.setdefault('v', defaultdict(int))
    for k, x in r['v'].items():
        vv[k] += x


def sorted_votes(v):
    return sorted(([k, x] for k, x in v.items() if x > 0), key=lambda r: -r[1])


# ---- leitura
res = {1: {}, 3: {}}
for uf in ['br'] + UFS + ['zz']:
    res[1][uf] = api(uf, 1)
for uf in GOV_UFS:
    res[3][uf] = api(uf, 3)
missing = [u for u, r in res[1].items() if not r]
assert not missing, f'faltam arquivos: {missing}'

acc = {1: defaultdict(dict), 3: defaultdict(dict)}
falta = []
for zid, z in BEL.items():
    if 'muns' not in z:
        continue
    uf, zona = z['uf'], zid[3:]
    for mun in z['muns']:
        for cg in ((1, 3) if uf in GOV_UFS else (1,)):
            r = api(uf, cg, f'{mun}-z{zona}')
            if r is None:
                falta.append(f'{uf}{mun}-z{zona} c{cg}')
                continue
            add(acc[cg][mun], r)
            add(acc[cg][zid], r)
            add(acc[cg]['soma-' + uf], r)
print('arquivos município-zona ausentes:', len(falta), falta[:10])
assert not falta, 'baixe os arquivos que faltam antes de gerar'

# conferência: soma das zonas = arquivo da UF; soma das UFs + exterior = Brasil
for cg in (1, 3):
    for uf in (UFS if cg == 1 else GOV_UFS):
        s, o = acc[cg]['soma-' + uf], res[cg][uf]
        if s['t'] != o['t'] or {k: x for k, x in s['v'].items() if x} != {k: x for k, x in o['v'].items() if x}:
            print(f'  AVISO {uf} c{cg}: soma das zonas {s["t"]} ≠ arquivo da UF {o["t"]}')
brs = [sum(res[1][u]['t'][i] for u in UFS + ['zz']) for i in range(6)]
print('Brasil: arquivo', res[1]['br']['t'], '| soma UFs+exterior', brs)

# ---- resumo e detalhes
PT = next(sq for sq, c in CANDS['br'].items() if c[1] == '13')
PL = next(sq for sq, c in CANDS['br'].items() if c[1] == '22')
summary = {}


def gov_summary(c3):
    vs = c3['v']
    if not vs or not c3['t'][2] or vs[0][1] == 0:
        return None
    second = vs[1][1] if len(vs) > 1 else 0
    return [CANDS[c3['uf']][vs[0][0]][2], round((vs[0][1] - second) / c3['t'][2], 4), vs[0][0]]


def put(key, name, uf, c, extra=None):
    c1 = c['1']
    d = dict(c1['v'])
    p = prev.get(key, {})
    g = gov_summary({**c['3'], 'uf': uf}) if '3' in c and not c['3'].get('list') else None
    summary[key] = {'n': name, 'uf': uf, 't26': c1['t'], 't22': p.get('t26'),
                    'p26': [d.get(PT, 0), d.get(PL, 0)], 'p22': p.get('p26'), 'g': g}
    if extra:
        summary[key].update(extra)
    dump(f'd/{key}.json', {'c': c})


def detail(key, uf, src):
    c = {}
    for cg in (1, 3):
        r = src(cg, key)
        if r and r['t'][0]:
            c[str(cg)] = {'t': r['t'], 'v': sorted_votes(r['v'])}
    return c


# Brasil: presidente + lista dos governadores
br = {'1': {'t': res[1]['br']['t'], 'v': sorted_votes(res[1]['br']['v'])}}
lst = []
for uf in GOV_UFS:
    r = res[3][uf]
    b = r['t'][2] + r['t'][5]
    for sq, x in r['v'].items():
        if x > 0:
            lst.append([sq, x, round(100 * x / b, 2) if b else 0, uf])
lst.sort(key=lambda r: -r[2])
put('br', 'Brasil', 'br', {**br, '3': {'v': lst, 'list': True}})
summary['br']['g'] = None

for uf in UFS + ['zz']:
    put(uf, UF_NAMES[uf], uf, detail(uf, uf, lambda cg, k: res[cg].get(k)))
for key, e in BEL.items():
    if len(key) == 5 and key.isdigit() and e['uf'] != 'zz':
        c = detail(key, e['uf'], lambda cg, k: acc[cg].get(k) or None)
        if c.get('1'):
            put(key, e['n'], e['uf'], c, {'ibge': e.get('ibge')})
    elif 'muns' in e:
        c = detail(key, e['uf'], lambda cg, k: acc[cg].get(k) or None)
        if c.get('1'):
            put(key, e['n'], e['uf'], c, {'muns': e['muns']})
for scope, d in CANDS.items():
    dump(f'cand/{scope}.json', d)
dump('summary.json', {'el': summary, 'uf': UF_NAMES, 'pt': PT, 'pl': PL,
                      'meta': {'ano': 2026, 'turno': 2, 'prev': '2022-2', 'right': 'PL', 'rightNum': '22',
                               'secoesSemVotos': True}})
print('resumo', len(summary))
os.makedirs(os.path.join(OUT, 'geo'), exist_ok=True)
shutil.copy(os.path.join(BASE, 'geo', 'zonas.json'), os.path.join(OUT, 'geo', 'zonas.json'))

# ---- seções: totais do 2º turno nos mesmos pontos do 1º turno
sec_t = {}
z = zipfile.ZipFile(DETALHE)
mem = next(m for m in z.namelist() if m.endswith('_BR.csv'))
with z.open(mem) as fh:
    for r in csv.DictReader(io.TextIOWrapper(fh, 'latin1'), delimiter=';'):
        if r['NR_TURNO'] != '2' or r['CD_CARGO'] != '1':
            continue
        n = lambda k: int(r[k] or 0)
        mun = 'zz' if r['SG_UF'] == 'ZZ' else r['CD_MUNICIPIO'].zfill(5)   # exterior: zona + seção bastam
        sec_t[(mun, n('NR_ZONA'), n('NR_SECAO'))] = [
            n('QT_APTOS'), n('QT_COMPARECIMENTO'), n('QT_VOTOS_NOMINAIS') + n('QT_VOTOS_LEGENDA'),
            n('QT_VOTOS_BRANCOS'), n('QT_VOTOS_NULOS'), 0]
print('seções no 2º turno', len(sec_t))


def tot(mun, secs):
    t = [0] * 6
    for zz, ss in secs:
        x = sec_t.get((mun, zz, ss))
        if x:
            for i in range(6):
                t[i] += x[i]
    return t


usadas = 0
for f in sorted(os.listdir(os.path.join(BASE, 's'))):
    uf = f[:-5]
    s = json.load(open(os.path.join(BASE, 's', f)))
    if uf == 'zz':
        out = []
        for p in s:
            t = tot('zz', p['s'])[:5]
            if t[0]:
                out.append({**p, 't': t, 'v': {}})
        dump('s/zz.json', out)
        print('pontos no exterior', len(out))
        continue
    sd_all = {m: json.load(open(os.path.join(BASE, 'sd', f'{m}.json'))) for m in s['muns']
              if os.path.exists(os.path.join(BASE, 'sd', f'{m}.json'))}
    n = len(s['names'])
    cols = {k: s[k] for k in ('m', 'lat', 'lon', 'ns', 'z', 'names', 'muns', 'parties')}
    for k in ('apt', 'comp', 'val', 'bra', 'nul', 'pt', 'pl', 'gm'):
        cols[k] = [0] * n
    cols['gp'] = [-1] * n
    cols['parties'] = []
    sd_out = defaultdict(dict)
    for i in range(n):
        mun = s['muns'][s['m'][i]]
        d = sd_all.get(mun, {}).get(str(i))
        if not d:
            continue
        t = tot(mun, d['s'])
        if t[0]:
            usadas += 1
        cols['apt'][i], cols['comp'][i], cols['val'][i], cols['bra'][i], cols['nul'][i] = t[:5]
        sd_out[mun][str(i)] = {'s': d['s'], 'c': {'1': [t, {}]} if t[0] else {}}
    dump(f's/{uf}.json', cols)
    for mun, d in sd_out.items():
        dump(f'sd/{mun}.json', d)
print('locais com totais do 2º turno', usadas)
