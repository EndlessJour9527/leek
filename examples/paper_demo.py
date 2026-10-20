"""Entirely synthetic example; run from the repository root as a module."""
from leek.ledger import Ledger


def main():
    account = Ledger('2000', ['SYNTH_A'])
    account.fill('SYNTH_A', 'BUY', '100', '10', '10.01', '1', '2024-01-01')
    account.record('SYNTH_A', 'synthetic-dividend')
    account.ex('SYNTH_A', 'synthetic-dividend', '1', '1', 'exact')
    assert account.nav({'SYNTH_A': '9'}) == 1998
    account.pay('SYNTH_A', 'synthetic-dividend')
    print('SYNTHETIC PAPER NAV:', account.nav({'SYNTH_A': '9'}))


if __name__ == '__main__':
    main()
