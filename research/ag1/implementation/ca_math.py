"""Price-basis transformations, separate from actual account rounding."""
from ledger import dec

def transformed_reference(previous_raw_close, cash_per_old_share, exact_share_ratio):
    prev,div,ratio=map(dec,(previous_raw_close,cash_per_old_share,exact_share_ratio))
    if prev<=0 or div<0 or ratio<=0 or prev<=div:
        raise ValueError('invalid corporate action price basis')
    return (prev-div)/ratio

def chain_total_return(previous_tr, previous_raw_close, current_basis_close, cash_per_old_share, exact_share_ratio):
    tr,prev,close,div,ratio=map(dec,(previous_tr,previous_raw_close,current_basis_close,cash_per_old_share,exact_share_ratio))
    if min(tr,prev,close,ratio)<=0 or div<0:
        raise ValueError('invalid corporate action TR inputs')
    return tr*(close*ratio+div)/prev
