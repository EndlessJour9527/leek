"""Day-only frozen-plan executor; no ranking, next-day HLC, or fallback winners."""
from decimal import Decimal as D, ROUND_FLOOR
from ledger import dec
from allocation import commission,capped_buy_quantity,common_scalar_allocation
from contract import DataBlocked,iso_date


def make_plan(plan_id, signal_date, execution_date, weights, targets, signal_closes, signal_nav, positions, lot_size, odd_lot_exit_allowed):
    if iso_date(signal_date)>=iso_date(execution_date):raise ValueError('execution must follow signal')
    lot=dec(lot_size);orders=[]
    for s in sorted(weights):
        current,target=positions[s]['qty'],dec(targets[s])
        delta=target-current
        if not delta:continue
        side='BUY' if delta>0 else 'SELL'
        qty=(abs(delta)/lot).to_integral_value(rounding=ROUND_FLOOR)*lot
        if side=='SELL' and not target and odd_lot_exit_allowed[s]:qty=current
        if qty:
            orders.append({'symbol':s,'side':side,'quantity':qty,'signal_planned_notional':qty*dec(signal_closes[s]),
                           'signal_weight_budget':dec(weights[s])*dec(signal_nav),'target_zero':target==0,
                           'odd_exit_allowed':odd_lot_exit_allowed[s]})
    return {'id':plan_id,'signal_date':signal_date,'execution_date':execution_date,'orders':orders,
            'weights':dict(weights),'signal_nav':dec(signal_nav),'signal_closes':dict(signal_closes)}


def transform_plan(plan,symbol,ratio,lot_size):
    """Mechanical theoretical conversion only; original CNY caps remain unchanged."""
    ratio,lot=dec(ratio),dec(lot_size)
    if min(ratio,lot)<=0:raise ValueError('invalid plan conversion')
    for order in plan['orders']:
        if order['symbol']==symbol:
            order['quantity']=(order['quantity']*ratio/lot).to_integral_value(rounding=ROUND_FLOOR)*lot


class OrderExecutor:
    def __init__(self):
        self.consumed=set()

    @staticmethod
    def block_reason(order,quote):
        if not quote:return 'missing_quote'
        status=quote.get('status')
        if status=='suspended_verified':return 'known_suspension'
        if status not in ('trading_verified','observed_daily_conditional'):return 'unknown_status'
        if status=='observed_daily_conditional' and quote.get('conditional_policy')!='CLARIFICATION_004':return 'unqualified_conditional_status'
        try:
            raw=dec(quote['open']);upper=dec(quote['upper_limit']);lower=dec(quote['lower_limit'])
            if raw<=0 or lower<=0 or upper<=lower:return 'invalid_open_or_limits'
        except (KeyError,ValueError,ArithmeticError):return 'missing_open_or_limits'
        if not quote.get('limit_evidence'):return 'unverified_price_limits'
        if order['side']=='BUY' and raw>=upper:return 'adverse_open_limit'
        if order['side']=='SELL' and raw<=lower:return 'adverse_open_limit'
        return None

    def execute(self,ledger,plan,quotes,date,cost,lot_size):
        if plan['id'] in self.consumed:raise ValueError('day-only plan already consumed')
        if date!=plan['execution_date']:raise ValueError('plan is not valid on this session')
        rate,minimum,slip=map(dec,(cost['commission_rate'],cost['minimum_commission_cny'],cost['adverse_slippage_rate']))
        if min(rate,minimum,slip)<0 or slip>=1:raise ValueError('invalid costs')
        lot=dec(lot_size)
        if lot<=0 or len({o['symbol'] for o in plan['orders']})!=len(plan['orders']):raise ValueError('invalid lot or duplicate orders')
        self.consumed.add(plan['id'])
        trades=[];rejected=[];buys={};prices={}
        for order in sorted(plan['orders'],key=lambda o:(o['side']!='SELL',o['symbol'])):
            s=order['symbol'];reason=self.block_reason(order,quotes.get(s))
            if reason:
                rejected.append(dict(symbol=s,side=order['side'],reason=reason,planned_quantity=order['quantity']));continue
            raw=dec(quotes[s]['open']);px=raw*(1+slip if order['side']=='BUY' else 1-slip)
            if order['side']=='BUY':
                q=capped_buy_quantity(order['quantity'],order['signal_planned_notional'],order['signal_weight_budget'],px,lot)
                buys[s]=q;prices[s]=px
            else:
                q=min(order['quantity'],ledger.sellable(s,date))
                if order['target_zero'] and order['odd_exit_allowed']:
                    # Corporate-action account rounding is mechanically realized, not a new ranking decision.
                    q=ledger.sellable(s,date)
                else:q=(q/lot).to_integral_value(rounding=ROUND_FLOOR)*lot
                if not q:
                    rejected.append(dict(symbol=s,side='SELL',reason='no_settled_lot',planned_quantity=order['quantity']));continue
                fee=commission(q*px,rate,minimum)
                if ledger.cash+q*px-fee<0:
                    rejected.append(dict(symbol=s,side='SELL',reason='sell_fee_exceeds_cash',planned_quantity=order['quantity']));continue
                before=ledger.cash;ledger.fill(s,'SELL',q,raw,px,fee,date)
                trades.append(dict(symbol=s,side='SELL',quantity=q,raw_open=raw,fill_price=px,commission=fee,cash_before=before,cash_after=ledger.cash))
        allocation=common_scalar_allocation(buys,prices,ledger.cash,lot,rate,minimum)
        for s in sorted(buys):
            q=allocation['quantities'][s]
            if not q:
                rejected.append(dict(symbol=s,side='BUY',reason='capped_or_unaffordable_lot',planned_quantity=buys[s]));continue
            raw=dec(quotes[s]['open']);px=prices[s];fee=commission(q*px,rate,minimum)
            before=ledger.cash;ledger.fill(s,'BUY',q,raw,px,fee,date)
            trades.append(dict(symbol=s,side='BUY',quantity=q,raw_open=raw,fill_price=px,commission=fee,cash_before=before,cash_after=ledger.cash))
        for t in trades:
            q=quotes[t['symbol']]
            t.update(notional=t['quantity']*t['fill_price'],slippage_cost=abs(t['fill_price']-t['raw_open'])*t['quantity'],status_evidence=q['status'],limit_evidence=q['limit_evidence'],first_print_time=q.get('first_print_time','unknown'),execution_evidence='CONDITIONAL_FIRST_PRINT_DAILY_PROXY')
        return {'plan_id':plan['id'],'signal_date':plan['signal_date'],'date':date,'trades':trades,'rejected':rejected,
                'allocation':allocation,'evidence_tier':'CONDITIONAL_FIRST_PRINT_DAILY_PROXY','same_open_sale_cash_assumed_available':True}
