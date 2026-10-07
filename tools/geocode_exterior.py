#!/usr/bin/env python3
"""Geocodifica os locais de votação no exterior (o TSE publica o endereço, mas não as
coordenadas) usando o Nominatim (OpenStreetMap), respeitando 1 consulta por segundo.

Uso: python3 tools/geocode_exterior.py <ext_locais.json>
Saída: tools/exterior_coords.json  {"<cód. cidade>-<nº local>": [lat, lon, "fonte"]}
A cidade é localizada primeiro; o resultado do endereço/nome do local só é aceito se ficar
a até 300 km da cidade (evita homônimos). Sem resultado, o local fica no ponto da cidade.
"""
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

UA = 'mapa-tse/1.0 (mapa das eleições 2026; github.com/Gussygussy/mapa-tse)'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exterior_coords.json')
GENERIC = {'CENTRO', '', 'EXTERIOR'}
_last = [0.0]


def search(q):
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


def main():
    locs = json.load(open(sys.argv[1]))
    res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    city_pt = {}
    for l in locs:
        country = l['bairro'] if l['bairro'].upper() not in GENERIC else ''
        key = l['cd']
        if key in city_pt:
            continue
        p = search(f"{l['city']}, {country}" if country else l['city']) or search(l['city'])
        city_pt[key] = p
        print('cidade', l['city'], country, p, flush=True)
    for i, l in enumerate(locs):
        key = f"{l['cd']}-{l['nr']}"
        if key in res:
            continue
        city = city_pt.get(l['cd'])
        country = l['bairro'] if l['bairro'].upper() not in GENERIC else ''
        got = None
        for src, q in (('endereço', f"{l['addr']}, {country}" if country else l['addr']),
                       ('endereço', l['addr']),
                       ('nome', f"{l['name']}, {l['city']}")):
            p = search(q)
            if p and (city is None or km(p, city) <= 300):
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
