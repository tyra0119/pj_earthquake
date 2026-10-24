"""前回ページを作ったとき（snapshot.json）より新しい地震だけを取って、latest.json に書く。
公開ページ（pj_earthquake）を開くと latest.json を読んで足す。pj_earthquake の GitHub Actions が毎朝これを動かす（2026-10-25 利用者「2」＝毎日自動で取り直す）。
ページ本体（12 MB）を毎日作り直してコミットすると、リポジトリが 1 年で数 GB になるので、新しい分だけの小さなファイルにしている。

  python scripts/build_latest.py snapshot.json latest.json

- USGS: snapshot の usgsLast より新しい、世界の M4.5 以上と日本付近の M2.5 以上
- 気象庁: 震源リスト（日ごと、暫定の値）の、snapshot の jmaEnd の日から最近までの、日本付近の M2 以上
Python の標準のものだけで動く（GitHub Actions でそのまま動かせるように）
"""
import datetime, html, json, re, sys, time, urllib.request

LON0, LON1, LAT0, LAT1 = 122.0, 150.0, 22.0, 48.0
UA = {'User-Agent': 'earthquake-3d (github.com/tyra0119/earthquake)'}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


snap = json.load(open(sys.argv[1], encoding='utf8'))
out_path = sys.argv[2]
now = datetime.datetime.now(datetime.timezone.utc)

# ---- USGS ----
start = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(minutes=snap['usgsLast'] + 1)
s, e = start.strftime('%Y-%m-%dT%H:%M:%S'), (now + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
B = f'https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&orderby=time-asc&starttime={s}&endtime={e}'
ev = {}
for url in (B + '&minmagnitude=4.5',
            B + f'&minmagnitude=2.5&minlatitude={LAT0:g}&maxlatitude={LAT1:g}&minlongitude={LON0:g}&maxlongitude={LON1:g}'):
    for ft in json.loads(fetch(url))['features']:
        p = ft['properties']; c = ft['geometry']['coordinates']
        if p.get('mag') is None or p.get('type') != 'earthquake':
            continue
        tmin = round(p['time'] / 60000)
        if tmin <= snap['usgsLast']:
            continue
        ev[ft['id']] = [tmin, round(c[1], 3), round(c[0], 3), round(max(c[2] or 0, 0), 1), round(p['mag'], 1)]
usgs = sorted(ev.values())

# ---- 気象庁の震源リスト（日ごと） ----
idx = fetch('https://www.data.jma.go.jp/eqev/data/daily_map/index.html').decode('utf8', 'replace')
first = snap['jmaEnd'].replace('-', '')
days = sorted(d for d in set(re.findall(r"(\d{8})\.html", idx)) if d >= first)
pat = re.compile(r"^(\d{4})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2}):(\d{2})\s+([\d.]+)\s+(\d+)°\s*([\d.]+)'([NS])\s+(\d+)°\s*([\d.]+)'([EW])\s+(\S+)?\s+(\S+)\s+(.*)$")
jma = []
for d in days:
    page = fetch(f'https://www.data.jma.go.jp/eqev/data/daily_map/{d}.html').decode('utf8', 'replace')
    time.sleep(0.5)  # 気象庁のサーバーに負担をかけないように
    i = page.find('<pre'); j = page.find('</pre>', i)
    for ln in html.unescape(re.sub(r'<[^>]+>', '', page[i:j])).splitlines():
        m = pat.match(ln.strip())
        if not m:
            continue
        try:
            mag = float(m.group(14))
        except ValueError:
            continue
        if mag < 2:
            continue
        lat = int(m.group(7)) + float(m.group(8)) / 60; lon = int(m.group(10)) + float(m.group(11)) / 60
        if m.group(9) == 'S': lat = -lat
        if m.group(12) == 'W': lon = -lon
        if not (LAT0 <= lat <= LAT1 and LON0 <= lon <= LON1):
            continue
        try:
            dep = float(m.group(13))
        except (TypeError, ValueError):
            dep = 0
        tj = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)))
        tmin = int((tj - datetime.datetime(1970, 1, 1)).total_seconds() // 60) - 540  # 日本時間 → UTC（1970 年からの分）
        jma.append([tmin, round(lat, 3), round(lon, 3), round(max(dep, 0), 1), mag])
jma.sort()
jma_end = (datetime.datetime.strptime(days[-1], '%Y%m%d') + datetime.timedelta(days=1)).date().isoformat() if days else snap['jmaEnd']

asof = (now + datetime.timedelta(hours=9)).date().isoformat()  # 日本時間の日付
out = {'asof': asof, 'from': snap, 'usgs': usgs, 'jma': jma, 'jmaEnd': jma_end}
with open(out_path, 'w', encoding='utf8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
print(f'latest.json: USGS {len(usgs)} 件、気象庁 {len(jma)} 件（{days[0] if days else "-"}〜{days[-1] if days else "-"}）、取得日 {asof}')
