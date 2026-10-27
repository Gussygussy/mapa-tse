import json, os, sys, time, threading, urllib.request, urllib.error, queue
OUT = sys.argv[2]
s = json.load(open(sys.argv[1]))['el']
GOV = ['ac', 'am', 'df', 'es', 'rn', 'to']
B = 'https://resultados.tse.jus.br/oficial/ele2026'
jobs = []
def add(ele, uf, cargo, suf=''):
    name = f'{uf}{suf}-c{cargo:04d}-e{ele:06d}-u.json'
    jobs.append((f'{B}/{ele}/dados/{uf}/{name}', os.path.join(OUT, name)))
ufs = ['br'] + sorted(k for k in s if len(k) == 2 and k != 'br')
for uf in ufs: add(6258, uf, 1)
for uf in GOV: add(6260, uf, 3)
for k, v in s.items():
    if 'muns' not in v: continue
    z = k[3:]
    for m in v['muns']:
        add(6258, v['uf'], 1, f'{m}-z{z}')
        if v['uf'] in GOV: add(6260, v['uf'], 3, f'{m}-z{z}')
jobs = [j for j in jobs if not os.path.exists(j[1])]
print('jobs', len(jobs), flush=True)
q = queue.Queue()
for j in jobs: q.put(j)
RATE = 2.3; lock = threading.Lock(); nxt = [time.time()]; slow = [0]; done = [0]; fail = []
def worker():
    while True:
        try: url, path = q.get_nowait()
        except queue.Empty: return
        for attempt in range(12):
            with lock:
                now = time.time(); r = RATE / (2.5 if slow[0] > now else 1)
                t = max(now, nxt[0]); nxt[0] = t + 1 / r
            time.sleep(max(0, t - time.time()))
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={'Accept-Encoding': 'identity'}), timeout=30) as resp:
                    data = resp.read()
                json.loads(data)
                open(path + '.tmp', 'wb').write(data); os.replace(path + '.tmp', path)
                break
            except urllib.error.HTTPError as e:
                if e.code == 404: fail.append((url, 404)); break
                if e.code == 429: slow[0] = time.time() + 30
                time.sleep(2)
            except Exception as e:
                time.sleep(3)
        else:
            fail.append((url, 'retries'))
        with lock:
            done[0] += 1
            if done[0] % 200 == 0: print(done[0], 'feitos', len(fail), 'falhas', flush=True)
ts = [threading.Thread(target=worker) for _ in range(6)]
for t in ts: t.start()
for t in ts: t.join()
print('fim', done[0], 'falhas', fail[:20], len(fail), flush=True)
