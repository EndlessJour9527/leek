"""Ex-post single-factor return audit. NOT a new strategy, trade replay, or holdout.

Run: python -m research.h002h003_sourcev1.risk_factor_audit --zip /PRIVATE/leek_h002h003_conditional_evidence_20261027.zip
Reads only historical derived NAV from the user's existing private bundle;
never fetches data, refits models, changes orders, or publishes raw OHLC.
"""
import argparse
import json
import math
import zipfile

EXPECTED_SHA = '7e0975c04227d0168b48f552d8e16d8313f11b1ca67dda240a03ac90dfe924e2'
SOURCE = 'ML001_SSE_TENCENT_PANEL_V1'
INITIAL_CASH = 50000.0
LAGS = (20, 60)


def series(account):
    rows = account['daily']
    if len(rows) != 1455 or rows[0]['date'] != '2020-01-02' or rows[-1]['date'] != '2025-12-31':
        raise ValueError('missing historical sessions')
    dates = [r['date'] for r in rows]
    if sorted(set(dates)) != dates:
        raise ValueError('date duplication or disorder')
    nav = [float(r['nav']) for r in rows]
    expo = [float(r['exposure']) for r in rows]
    if not all(math.isfinite(v) and v > 0 for v in nav):
        raise ValueError('nonpositive NAV')
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in expo):
        raise ValueError('invalid exposure')
    summary = account['summary']
    if abs(nav[-1]-float(summary['terminal_nav'])) > .00001:
        raise ValueError('wrong terminal NAV')
    if abs(100*(nav[-1]/INITIAL_CASH-1)-float(summary['total_return_pct'])) > .00001:
        raise ValueError('wrong total return')
    if abs(100*math.fsum(expo)/len(expo)-float(summary['mean_exposure_pct'])) > .00001:
        raise ValueError('wrong exposure')
    prior = INITIAL_CASH
    ret = []
    for value in nav:
        ret.append(value/prior-1)
        prior = value
    return dates, expo, ret


def regress_hac(y, benchmark, lag=20):
    n = len(y)
    if n != len(benchmark) or n <= lag + 2:
        raise ValueError('short or unpaired histories')
    sx, sy = math.fsum(benchmark), math.fsum(y)
    sxx = math.fsum(v*v for v in benchmark)
    sxy = math.fsum(v*w for v,w in zip(y,benchmark))
    det = n*sxx-sx*sx
    if det <= 1e-15:
        raise ValueError('degenerate benchmark')
    beta = (n*sxy-sx*sy)/det
    alpha = (sy-beta*sx)/n
    err = [a-alpha-beta*b for a,b in zip(y,benchmark)]
    score0 = err
    score1 = [a*b for a,b in zip(err,benchmark)]

    def long_cov(a,b):
        total=math.fsum(v*w for v,w in zip(a,b))
        for k in range(1,lag+1):
            weight=1-k/(lag+1)
            total+=weight*(math.fsum(a[t]*b[t-k] for t in range(k,n))
                           +math.fsum(a[t-k]*b[t] for t in range(k,n)))
        return total

    i00,i01,i11=sxx/det,-sx/det,n/det
    s00,s01,s11=long_cov(score0,score0),long_cov(score0,score1),long_cov(score1,score1)
    variance=(i00*s00+i01*s01)*i00+(i00*s01+i01*s11)*i01
    if variance < -1e-20:
        raise ValueError('invalid HAC covariance')
    half=1.96*math.sqrt(max(0,variance))*252*100
    return dict(beta=round(beta,6),annual_arithmetic_intercept_pct=round(alpha*252*100,6),
                hac_approx_95pct=[round(alpha*252*100-half,6),round(alpha*252*100+half,6)],lag=lag)


def audit(blob):
    fp=blob['fingerprint']
    if fp.get('data_version')!=SOURCE or fp.get('private_dataset_sha256')!=EXPECTED_SHA:
        raise ValueError('different or tampered research panel fingerprint')
    accounts=blob['accounts'];out={}
    for case in ('base','stress'):
        pdays,pexp,pret=series(accounts[case+'__buy_hold'])
        for model in ('h002_channel_20_10','h003_close_tr_bb20_2'):
            key=case+'__'+model
            days,exp,ret=series(accounts[key])
            if days!=pdays:raise ValueError('unaligned calendar')
            out[key]=dict(sessions=len(days),closed_trades=len(accounts[key]['closed_trades']),
                          mean_exposure_pct=round(100*math.fsum(exp)/len(exp),6),
                          passive_exposure_pct=round(100*math.fsum(pexp)/len(pexp),6),
                          hac={str(lag):regress_hac(ret,pret,lag) for lag in LAGS})
    return dict(date='2026-10-29',status='DESCRIPTIVE_EX_POST_AUDIT_ONLY',
                data_version=SOURCE,private_dataset_sha256=EXPECTED_SHA,
                sample='SEEN_DEVELOPMENT',new_training=0,new_trading_backtests=0,
                new_strategy_candidates=0,automatic_promotion=False,
                method='daily NAV returns versus same-cost passive; OLS constant/beta; Bartlett Newey-West HC0 with lags 20/60; 252x arithmetic annualization',
                limits=['single factor is not a matched-risk trade replay','post-selection CI does not correct selection bias',
                        'no new raw data or genuine forward sample','not a deployable alpha estimate'],results=out)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip',required=True,help='Private existing 2026-10-27 derived-account evidence ZIP')
    args=parser.parse_args()
    with zipfile.ZipFile(args.zip) as z:
        blob=json.loads(z.read('RESULTS_private_account_details.json'))
    print(json.dumps(audit(blob),ensure_ascii=False,sort_keys=True,indent=2))


if __name__=='__main__':main()
