#!/usr/bin/env python3
"""Geocodifica os locais de votação no exterior (o TSE publica o endereço, mas não as
coordenadas) usando o Nominatim (OpenStreetMap), respeitando 1 consulta por segundo.

Uso: python3 tools/geocode_exterior.py <ext_locais.json>
Saída: tools/exterior_coords.json  {"<cód. cidade>-<nº local>": [lat, lon, "fonte"]}
A cidade-sede é localizada primeiro (com correções manuais para homônimos); o resultado do
endereço/nome do local só é aceito se ficar a até 1.000 km dela (jurisdições consulares são
grandes, ex.: Nagóia cobre Hiroshima). Sem resultado, o local fica no ponto da cidade.
Rodar de novo só refaz os locais que ainda estão no ponto da cidade.
"""
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

UA = 'mapa-tse/1.0 (mapa das eleições 2026; github.com/Gussygussy/mapa-tse)'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exterior_coords.json')
GENERIC = {'CENTRO', '', 'EXTERIOR'}
MAX_KM = 1000
# cidades que o Nominatim confunde com homônimos (código TSE da cidade não é usado aqui: nome)
CITY_FIX = {
    'ATLANTA': (33.749, -84.388),
    'CASTRIES': (14.0101, -60.9875),
    'RIVERA': (-30.9053, -55.5508),
    'SAINT JOHNS': (17.1274, -61.8468),
    'SANTIAGO': (-33.4489, -70.6693),
    'SÃO JOSÉ': (9.9281, -84.0907),
    'ST GEORGES DE LOYAPOCK': (3.8906, -51.8058),
}
_cache = {}
_last = [0.0]


def search(q):
    q = q.strip(' ,-')
    if not q:
        return None
    if q in _cache:
        return _cache[q]
    _cache[q] = _search(q)
    return _cache[q]


def _search(q):
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
        {'q': q, 'format': 'json', 'limit': 1, 'accept-language': 'pt,en'})
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                _last[0] = time.time()
                d = json.load(r)
                return (float(d[0]['lat']), float(d[0]['lon'])) if d else None
        except Exception as e:  # rede instável: tenta de novo
            print('  erro', e, file=sys.stderr)
            time.sleep(3 * (attempt + 1))
    return None


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def clean_addr(a):
    """tira sala/suíte/andar/edifício, parênteses, CEPs e sufixos do tipo '- HALL 2'"""
    a = re.sub(r'\(.*?\)', ' ', a)
    a = re.sub(r'\b(SUITE|STE|SALA|PISO|ANDAR|FLOOR|FL|EDF|EDIF[IÍ]CIO|APT|UNIT|ROOM|HALL)\b[^,]*', ' ', a, flags=re.I)
    a = re.sub(r'\s+-\s+.*$', '', a)
    a = re.sub(r'\s*,(\s*,)+', ',', a)
    return re.sub(r'\s+', ' ', a).strip(' ,')


def queries(l, country):
    addr, name, city = l['addr'], l['name'], l['city']
    ca = clean_addr(addr)
    parts = [p.strip() for p in ca.split(',') if p.strip()]
    nm = re.sub(r'\(.*?\)', '', name).split(' - ')[0].strip()
    qs = [('endereço', f"{addr}, {country}" if country else addr), ('endereço', addr),
          ('endereço', f"{ca}, {country}" if country else ca),
          ('endereço', ', '.join(parts[:2] + [city]) if len(parts) > 1 else ''),
          ('nome', f"{nm}, {city}")]
    up = name.upper()
    if 'CONSULADO' in up:
        qs += [('nome', f"Consulate General of Brazil, {city}"), ('nome', f"Consulado do Brasil, {city}")]
    if 'EMBAIXADA' in up:
        qs += [('nome', f"Embassy of Brazil, {city}"), ('nome', f"Embaixada do Brasil, {city}")]
    return qs


def main():
    locs = json.load(open(sys.argv[1]))
    res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    city_pt = {}
    for l in locs:
        country = l['bairro'] if l['bairro'].upper() not in GENERIC else ''
        key = l['cd']
        if key in city_pt:
            continue
        p = CITY_FIX.get(l['city']) or search(f"{l['city']}, {country}" if country else l['city']) or search(l['city'])
        city_pt[key] = p
        print('cidade', l['city'], country, p, flush=True)
    for i, l in enumerate(locs):
        key = f"{l['cd']}-{l['nr']}"
        # refaz os que ficaram no ponto da cidade e os das cidades corrigidas
        if key in res and not res[key][2].startswith('cidade') and l['city'] not in CITY_FIX:
            continue
        city = city_pt.get(l['cd'])
        country = l['bairro'] if l['bairro'].upper() not in GENERIC else ''
        got = None
        for src, q in queries(l, country):
            p = search(q)
            if p and (city is None or km(p, city) <= MAX_KM):
                got = [round(p[0], 6), round(p[1], 6), src]
                break
        if got is None and city:
            got = [round(city[0], 6), round(city[1], 6), 'cidade']
        if got:
            res[key] = got
        print(i, l['city'], '|', l['name'][:40], '->', got, flush=True)
        if i % 20 == 0:
            json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=0)
    json.dump(res, open(OUT, 'w'), ensure_ascii=False, indent=0)
    print('fim', len(res), 'de', len(locs))


main()
