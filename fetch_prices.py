#!/usr/bin/env python3
"""每日收盤價更新（在 GitHub Actions 上跑）：用 Yahoo Finance chart API 抓每檔
最新收盤、日漲跌%、YTD%。無 API key。抓失敗的個股保留上一版數值，不覆蓋成 null。"""
import json, urllib.request, sys, os, datetime, time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = json.load(open(os.path.join(HERE, 'dashboard_data.json')))
pj_path = os.path.join(HERE, 'prices.json')
prev = {}
if os.path.exists(pj_path):
    try: prev = json.load(open(pj_path)).get('prices', {})
    except Exception: prev = {}

YEAR = datetime.date.today().year

def yahoo_sym(tk):
    special = {'HPS.A': 'HPS-A.TO'}  # 多倫多掛牌
    if tk in special: return special[tk]
    return tk.replace('.', '-')

def fetch(tk):
    sym = yahoo_sym(tk)
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1y'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/537.36'})
    with urllib.request.urlopen(req, timeout=25) as r:
        j = json.load(r)
    res = j['chart']['result'][0]
    meta = res['meta']
    ts = res['timestamp']
    closes = res['indicators']['quote'][0]['close']
    # 取出所有非 null 的 (date, close)，用時間序列算「當日」漲跌與 YTD
    series = [(datetime.datetime.utcfromtimestamp(t).date(), c)
              for t, c in zip(ts, closes) if c is not None]
    if len(series) < 2: return None
    last_date, price = series[-1]
    prev_close = series[-2][1]                       # 前一交易日收盤 → 正確的當日漲跌
    chg = (price/prev_close - 1)*100 if prev_close else None
    # YTD：今年 1/1 之前最後一筆收盤當基準
    base = None
    for d, c in series:
        if d < datetime.date(YEAR, 1, 1):
            base = c
    ytd = (price/base - 1)*100 if base else None
    last_date = last_date.isoformat()
    if price is None: return None
    return {'price': round(price, 2),
            'change_pct': round(chg, 2) if chg is not None else None,
            'ytd': round(ytd, 1) if ytd is not None else None,
            'date': last_date}

out, ok = {}, 0
for d in DATA:
    tk = d['ticker']
    rec = None
    for attempt in range(2):
        try:
            rec = fetch(tk); break
        except Exception as e:
            sys.stderr.write(f'{tk} attempt{attempt} failed: {e}\n'); time.sleep(1.5)
    if rec: out[tk] = rec; ok += 1
    elif tk in prev: out[tk] = prev[tk]
    time.sleep(0.4)

dates = [v.get('date') for v in out.values() if v.get('date')]
disp = max(dates) if dates else datetime.date.today().isoformat()
json.dump({'updated': disp, 'generated': datetime.date.today().isoformat(), 'prices': out},
          open(pj_path, 'w'), ensure_ascii=False, indent=1)
print(f'prices.json: {ok}/{len(DATA)} fetched, display date {disp}')
if ok < len(DATA)*0.6:
    sys.stderr.write('WARN: <60% fetched — source may be blocking Actions IPs\n')
