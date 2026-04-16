import requests

# Must pass auth cookie since login_required is enforced
session = requests.Session()

# Login first
login_resp = session.post('http://127.0.0.1:8001/api/v1/login',
    json={'username': 'Admin', 'password': 'SPAdmin@123'}, timeout=5)
print('Login:', login_resp.status_code)

# If login doesn't work via POST, set cookie directly
session.cookies.set('sr_pro_session', 'authenticated_admin')

tickers = ['RELIANCE', 'HDFCBANK', 'INFY', 'SBIN']
strategies = ['SR', 'SWING', 'DEMAND_SUPPLY']

for t in tickers:
    for strat in strategies:
        try:
            url = 'http://127.0.0.1:8001/api/v1/dashboard'
            r = session.get(url, params={'symbol': t, 'tf': '1D', 'strategy': strat}, timeout=30)
            if r.status_code == 200:
                d = r.json()
                sm = d.get('summary', {})
                sr = d.get('strategy', {})
                signal = sm.get('trade_signal', '?')
                side   = sm.get('side', '?')
                conf   = sm.get('confidence', '?')
                status_val = sr.get('entryStatus', '?')
                print(t + ' [' + strat + '] signal=' + str(signal) + ' side=' + str(side) + ' conf=' + str(conf) + '% entryStatus=' + str(status_val))
            else:
                print(t + ' [' + strat + ']: HTTP ' + str(r.status_code))
        except Exception as e:
            print(t + ' [' + strat + ']: ERROR - ' + str(e))
print('Done.')
