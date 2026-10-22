"""CA1 frozen two-stage allocation. Standard library; conditional daily-open proxy.
Reuses the unmodified Leek Ledger (vendor/ledger.py). Exact cent costs are passed
as its all-in commission at raw price; reporting components are kept separately.
FIFO basis is a descriptive overlay reconciled to ledger quantities and NAV.
"""
from decimal import Decimal as D, ROUND_HALF_UP
from fractions import Fraction
from datetime import date
from math import ceil, sqrt
import json, hashlib
from pathlib import Path
from vendor.ledger import Ledger
CODES=('510300','511010','518880')
ZERO=D(0)
def cent(x): return D(x).quantize(D('.01'),rounding=ROUND_HALF_UP)
def tick(x): return D(x).quantize(D('.001'),rounding=ROUND_HALF_UP)
def fee_parts(n,m=1):
    n=cent(n); return max(D(5*m),cent(n*D('.001')*m)),cent(n*D('.001')*m)
def cost(q,p,m=1):
    n=cent(D(q)*D(p)); f,s=fee_parts(n,m); return n,f,s
def reserve(q,p,m=1): return sum(cost(q,D(p)*D('1.02'),m))
def budgets(nav,weights):
    out={s:cent(nav*D(weights[s].numerator)/D(weights[s].denominator)) for s in CODES}
    excess=max(ZERO,sum(out.values())-nav)
    if excess: out[[s for s in CODES if weights[s]][-1]]-=excess
    return out
def affordable(ceiling,budget,cash,p,m):
    q=int(ceiling)//100*100
    while q and reserve(q,p,m)>min(budget,cash): q-=100
    return q
def eligibility(bar,prev,div,side,lock=None):
    if bar.get('suspended') or bar.get('unknown_ca') or bar.get('inconsistent_reference'): return 'BLOCKED_STATUS_CA'
    o=D(bar['open']); ref=tick(D(prev)-D(div))
    if o<=0 or ref<=0: return 'INVALID_PRICE'
    lo,hi=tick(ref*D('.90')),tick(ref*D('1.10'))
    if (bar.get('official_lower') is None) != (bar.get('official_upper') is None): raise ValueError('INCOMPLETE_OFFICIAL_LIMIT')
    if bar.get('official_lower') is not None and (D(bar['official_lower'])!=lo or D(bar['official_upper'])!=hi): raise ValueError('LIMIT_EVIDENCE_CONFLICT')
    if o<=lo or o>=hi: return 'MODEL_LIMIT_BOUNDARY'
    if side=='BUY' and not D('-.02') <= o/D(lock)-1 <= D('.02'): return 'BUY_GAP'
    return None

def validate(data):
    ds=data['calendar']; assert ds and ds==sorted(set(ds))
    for s in CODES:
        assert set(ds)<=set(data['bars'][s])
        for d in ds:
            b=data['bars'][s][d]; vals=[D(b[k]) for k in ('open','high','low','close')]
            assert all(v.is_finite() and v>0 for v in vals)
            o,h,l,c=vals; assert l<=min(o,c)<=max(o,c)<=h
    ids=set()
    for e in data['events']:
        assert e['id'] not in ids; ids.add(e['id'])
        assert e['symbol'] in CODES and e['record']<e['ex']<=e['pay'] and e['published']<=e['record']
        assert D(e['amount'])>=0 and e['ratio']=='1'
        assert all(e[k] in ds for k in ('record','ex','pay'))

def weights_for(account):
    return {s: Fraction(1,3) if account=='CA1' or account=='SCASH' and s=='510300' else Fraction(1) if account=='BH300' and s=='510300' else Fraction(0) for s in CODES}

def replay(data,account='CA1',multiple=1):
    validate(data); ds=data['calendar']; bars=data['bars']; events=data['events']; weights=weights_for(account)
    ledger=Ledger('50000',CODES); lots={s:[] for s in CODES}; restricted=[]; orders=[]; cycles=[]; daily=[]; ca=[]; closed=[]
    all_lots=[]; record_lots={}; episodes=[]; active_episodes={}
    total_fee=ZERO; total_slip=ZERO; div_total=ZERO; principal=ZERO; cycle=None
    def qty(s): return int(ledger.positions[s]['qty'])
    def known_cancel(s,t,buy,asof): return any(e['symbol']==s and t<e['ex']<=buy and e['published']<=asof for e in events)
    for j,d in enumerate(ds):
        cash_start=ledger.cash; incoming=ZERO; cashflow=ZERO
        restricted=[r for r in restricted if r['release']>d]
        for e in events:
            if e['ex']==d:
                if e['published']>=d: raise ValueError('CA_NOT_KNOWN_PREOPEN')
                ledger.ex(e['symbol'],e['id'],e['amount'],'1','exact')
                key=(e['symbol'],e['id']); ledger.receivables[key]=cent(ledger.receivables[key]); div_total+=ledger.receivables[key]
                alloc=ZERO; entitled=record_lots[e['id']]
                for k,(lot,nshares) in enumerate(entitled):
                    amount=ledger.receivables[key]-alloc if k==len(entitled)-1 else cent(D(nshares)*D(e['amount']))
                    lot['income']+=amount; episodes[lot['episode']]['income']+=amount; alloc+=amount
                assert alloc==ledger.receivables[key]
                ca.append(dict(date=d,phase='EX',event=e['id'],amount=ledger.receivables[key],entitled=ledger.entitlements[key]))
        for order in [o for o in orders if o['execute']==d and o['status']=='LOCKED']:
            s=order['symbol']; side=order['side']; q=order['quantity']; o=D(bars[s][d]['open']); prior=D(bars[s][ds[j-1]]['close'])
            div=sum((D(e['amount']) for e in events if e['symbol']==s and e['ex']==d),ZERO)
            reason='CA_CYCLE_CANCELLED' if known_cancel(s,order['signal'],order['cycle_buy'],ds[j-1]) else eligibility(bars[s][d],prior,div,side,order.get('lock_close'))
            n,f,sl=cost(q,o,multiple); spendable=ledger.cash-sum((r['amount'] for r in restricted),ZERO)
            if not reason and side=='BUY' and n+f+sl>spendable: reason='INSUFFICIENT_CASH'
            if not reason and side=='SELL' and q>ledger.sellable(s,d): reason='INSUFFICIENT_SELLABLE'
            if reason: order.update(status='NO_FILL',reason=reason,fill_quantity=0); continue
            before=ledger.cash
            if side=='BUY' and not qty(s):
                active_episodes[s]=len(episodes); episodes.append(dict(symbol=s,entry=d,buys=ZERO,sells=ZERO,income=ZERO,exit=None))
            episode=episodes[active_episodes[s]]
            ledger.fill(s,side,q,o,o,f+sl,d)
            total_fee+=f; total_slip+=sl; ledger.commission=total_fee; ledger.slippage=total_slip
            cashflow+=ledger.cash-before; principal+=n
            if side=='BUY':
                episode['buys']+=n+f+sl
                lot=dict(episode=active_episodes[s],id=f'{s}:{d}:{len(all_lots)}',symbol=s,date=d,quantity=q,bought_quantity=q,basis=n+f+sl,original_cost=n+f+sl,net_sales=ZERO,income=ZERO)
                lots[s].append(lot); all_lots.append(lot)
            else:
                episode['sells']+=n-f-sl
                if not qty(s): episode['exit']=d
                left=q; allocated_fee=ZERO; allocated_slip=ZERO
                for lot in lots[s]:
                    if not left: break
                    take=min(left,lot['quantity']); original=lot['quantity']
                    if not take: continue
                    basis=lot['basis'] if take==original else cent(lot['basis']*D(take)/original)
                    sale_fee=(f-allocated_fee) if take==left else cent(f*D(take)/q)
                    sale_slip=(sl-allocated_slip) if take==left else cent(sl*D(take)/q)
                    allocated_fee+=sale_fee; allocated_slip+=sale_slip; sale_alloc=sale_fee+sale_slip; net=cent(D(take)*o)-sale_alloc-basis
                    closed.append(dict(symbol=s,entry=lot['date'],exit=d,quantity=take,basis=basis,sell_cost=sale_alloc,sell_fee=sale_fee,sell_slippage=sale_slip,net_pnl=net))
                    lot['net_sales']+=cent(D(take)*o)-sale_alloc; lot['last_exit']=d
                    lot['quantity']-=take; lot['basis']-=basis; left-=take
                assert left==0 and allocated_fee==f and allocated_slip==sl
                lots[s]=[l for l in lots[s] if l['quantity']]
                release=ds[j+1] if j+1<len(ds) else '9999-12-31'
                restricted.append(dict(amount=n-f-sl,release=release))
            ledger.positions[s]['basis']=sum((l['basis'] for l in lots[s]),ZERO)
            order.update(status='FILL',fill_quantity=q,raw_open=o,notional=n,fee=f,slippage=sl,cash_before=before,cash_after=ledger.cash,assumption='SUFFICIENT_OPENING_LIQUIDITY_MODEL_LIMIT_PROXY')
        closes={s:D(bars[s][d]['close']) for s in CODES}
        for e in events:
            if e['record']==d:
                ledger.record(e['symbol'],e['id']); record_lots[e['id']]=[(l,l['quantity']) for l in lots[e['symbol']]]; ca.append(dict(date=d,phase='RECORD',event=e['id'],quantity=qty(e['symbol'])))
            if e['pay']==d:
                amount=ledger.pay(e['symbol'],e['id']); incoming+=amount; ca.append(dict(date=d,phase='PAY',event=e['id'],amount=amount))
        assert ledger.cash==cash_start+cashflow+incoming
        nav=ledger.nav(closes)
        if cycle and cycle['sell']==d:
            buying_power=ledger.cash # all today's restricted sale proceeds release next day
            for s in CODES:
                ceiling=cycle['buy_ceiling'][s]
                if not ceiling: continue
                reason=None
                if known_cancel(s,cycle['signal'],cycle['buy'],d): reason='CA_CYCLE_CANCELLED'
                budget=max(ZERO,cent(cycle['budgets'][s]-D(qty(s))*cycle['closes'][s]))
                q=0 if reason else affordable(ceiling,budget,buying_power,closes[s],multiple)
                r=reserve(q,closes[s],multiple) if q else ZERO
                orders.append(dict(signal=cycle['signal'],cycle_buy=cycle['buy'],lock=d,execute=cycle['buy'],symbol=s,side='BUY',quantity=q,status='LOCKED' if q else 'NO_ORDER',reason=reason or (None if q else 'LOT_BUDGET_CASH'),reserved=r,lock_close=closes[s],leg_budget=budget,ceiling=ceiling))
                buying_power-=r
        is_signal=j==0 or j+1<len(ds) and ds[j+1][:7]!=d[:7]
        if is_signal and j+2<len(ds) and account!='CASH' and (account!='BH300' or j==0):
            bs=budgets(nav,weights); targets={s:int(bs[s]/closes[s]/100)*100 for s in CODES}
            cycle=dict(signal=d,sell=ds[j+1],buy=ds[j+2],nav=nav,budgets=bs,closes=closes.copy(),targets=targets,buy_ceiling={s:max(0,targets[s]-qty(s)) for s in CODES})
            cycles.append(cycle)
            for s in CODES:
                q=max(0,qty(s)-targets[s])
                if q:
                    cancel=known_cancel(s,d,cycle['buy'],d)
                    orders.append(dict(signal=d,cycle_buy=cycle['buy'],lock=d,execute=cycle['sell'],symbol=s,side='SELL',quantity=q,status='NO_FILL' if cancel else 'LOCKED',reason='CA_CYCLE_CANCELLED' if cancel else None,reserved=ZERO))
        res=sum((o['reserved'] for o in orders if o['status']=='LOCKED' and o['side']=='BUY'),ZERO)
        rest=sum((r['amount'] for r in restricted),ZERO)
        assert ledger.cash>=rest>=0 and ledger.cash-res>=0
        pos={s:dict(quantity=qty(s),close=closes[s],value=D(qty(s))*closes[s],basis=ledger.positions[s]['basis'],unrealized=D(qty(s))*closes[s]-ledger.positions[s]['basis'],weight=D(qty(s))*closes[s]/nav) for s in CODES}
        assert all(D(sum(l['quantity'] for l in lots[s]))==ledger.positions[s]['qty'] for s in CODES)
        recv=sum(ledger.receivables.values(),ZERO)
        assert nav==ledger.cash+recv+sum((p['value'] for p in pos.values()),ZERO)
        realized=sum((x['net_pnl'] for x in closed),ZERO)
        assert abs(nav-D(50000)-realized-sum((p['unrealized'] for p in pos.values()),ZERO)-div_total)<D('.00001')
        daily.append(dict(date=d,nav=nav,cash=ledger.cash,restricted=rest,reserved=res,cash_unrestricted_before_reservations=ledger.cash-rest,execution_date=(ds[j+1] if j+1<len(ds) else None),execution_date_power_net_reserved=ledger.cash-res,receivable=recv,positions=pos,fees=total_fee,slippage=total_slip,dividend_income=div_total,realized=realized))
    return dict(account=account,cost='BASE' if multiple==1 else 'DOUBLE',grade='INPUTS_BOUNDED_CONDITIONAL_OPEN_PROXY',daily=daily,cycles=cycles,orders=orders,corporate_actions=ca,closed_fifo=closed,round_trips=[dict(e,net_pnl=e['sells']+e['income']-e['buys']) for e in episodes if e['exit']],episodes=episodes,open_lots=[l for l in all_lots if l['quantity']],turnover_principal=principal)

def metric(rows,initial=D(50000),principal=ZERO):
    navs=[float(r['nav']) for r in rows]; prev=float(initial); returns=[]; peak=prev; mdd=0; water=0; spell=0; maxspell=0
    for n in navs:
        returns.append(n/prev-1); prev=n; peak=max(peak,n); mdd=max(mdd,1-n/peak)
        if n<peak: water+=1; spell+=1; maxspell=max(maxspell,spell)
        else: spell=0
    days=(date.fromisoformat(rows[-1]['date'])-date.fromisoformat(rows[0]['date'])).days+1
    avg=sum(returns)/len(returns); var=sum((x-avg)**2 for x in returns)/len(returns)
    return dict(final_nav=navs[-1],total_return=navs[-1]/float(initial)-1,cagr=(navs[-1]/float(initial))**(365.25/days)-1,mdd=mdd,volatility=sqrt(252*var),ce3=252*avg-1.5*252*var,es05=sum(sorted(returns)[:ceil(.05*len(returns))])/ceil(.05*len(returns)),underwater_days=water,max_underwater_spell=maxspell,turnover=float(principal)/(sum(navs)/len(navs)),mean_weights={s:sum(float(r['positions'][s]['weight']) for r in rows)/len(rows) for s in CODES})

def summarize(report):
    rows=report['daily']; m=metric(rows,principal=report['turnover_principal']); trades=report['round_trips']; wins=[float(t['net_pnl']) for t in trades if t['net_pnl']>0]; losses=[float(t['net_pnl']) for t in trades if t['net_pnl']<0]
    m.update(closed_fifo_slices=len(report['closed_fifo']),complete_round_trips=len(trades),wins=len(wins),win_rate=len(wins)/len(trades) if trades else None,average_win=sum(wins)/len(wins) if wins else None,average_loss=sum(losses)/len(losses) if losses else None,net_expectancy=sum(float(t['net_pnl']) for t in trades)/len(trades) if trades else None,fees=float(rows[-1]['fees']),slippage=float(rows[-1]['slippage']),dividends=float(rows[-1]['dividend_income']),final_cash=float(rows[-1]['cash']),no_order=sum(o['status']=='NO_ORDER' for o in report['orders']),no_fill=sum(o['status']=='NO_FILL' for o in report['orders']))
    segments=[]
    for a,b in [('2021-10-18','2022-12-30'),('2023-01-03','2024-12-31'),('2025-01-02','2026-06-30')]:
        subset=[r for r in rows if a<=r['date']<=b]
        if not subset: continue
        prev=[r for r in rows if r['date']<a]; initial=prev[-1]['nav'] if prev else D(50000)
        segment_metric=metric(subset,initial); segment_metric['turnover']=None
        segments.append(dict(start=a,end=b,**segment_metric))
    m['segments']=segments
    return m

def economics(summaries):
    results={}
    for c in ('BASE','DOUBLE'):
        a,b=summaries['CA1_'+c],summaries['SCASH_'+c]
        if len(a['segments'])!=3 or len(b['segments'])!=3: raise ValueError('INCOMPLETE_SEGMENTS')
        stable=sum(x['cagr']>=y['cagr'] for x,y in zip(a['segments'],b['segments']))>=2
        gates=dict(cagr=D(str(a['cagr']))-D(str(b['cagr']))>=D('.01'),ce3=a['ce3']>b['ce3'],drawdown=D(str(a['mdd']))<=D(str(b['mdd']))+D('.05'),stability=stable)
        results[c]=dict(gates=gates,passed=all(gates.values()))
    results['decision']='RETAIN_FOR_FURTHER_EVIDENCE' if all(results[c]['passed'] for c in ('BASE','DOUBLE')) else 'STOP_CURRENT_VARIANT'
    return results

def subscription(rows):
    days=(date.fromisoformat(rows[-1]['date'])-date.fromisoformat(rows[0]['date'])).days+1
    out=[]
    for fx in (6,7,8):
        expense=cent(D(1200)*D(days)/D('365.25')*fx)
        out.append(dict(fx_scenario=fx,expense=expense,expense_fraction_initial=expense/50000,terminal_surplus=cent(rows[-1]['nav']-50000-expense),capital_burdens={str(p):str(D(1200)*fx/p) for p in (10000,50000,100000,200000)}))
    return out

def dump(path,obj): Path(path).write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2,default=lambda x: str(x))+'\n')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def fixed_fill_double(report):
    """Counterfactual cost diagnostic; keeps base fills, detects funding deficit.
    Not a valid recomputed execution path, no alteration to base ledger.
    """
    extra=ZERO; rows=[]; deficit=False
    for row in report['daily']:
        for o in report['orders']:
            if o['status']=='FILL' and o['execute']==row['date']:
                f,s=fee_parts(o['notional'],2); extra+=f+s-o['fee']-o['slippage']
                if o['cash_after']-extra<0: deficit=True
        cash=row['cash']-extra; deficit=deficit or cash<0
        rows.append(dict(date=row['date'],cash=cash,nav=row['nav']-extra,cumulative_extra_cost=extra))
    return dict(label='BASE_FIXED_FILLS_DOUBLE_COST_NOT_EXECUTABLE',funding_deficit=deficit,daily=rows,final_nav=rows[-1]['nav'])
