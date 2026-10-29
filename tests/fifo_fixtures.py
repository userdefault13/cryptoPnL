"""SYNTHETIC golden FIFO fixtures (hand-built, NOT chain data). Assets, prices, blocks and tx hashes are made up so the expected
values can be computed by hand (see the comments in tests/test_fifo_golden.py). Every price is > 0; nothing here is a market price."""
from decimal import Decimal as D
from cryptopnl.fifo import Entry, Mark

class Book:
    """Builds Entry rows with increasing ids; one call to tx() = one synthetic transaction at a block."""
    def __init__(self): self.rows = []; self._id = 0; self._tx = 0
    def tx(self, block, *legs, tx_index=0):
        self._tx += 1; h = f"0xfixture{self._tx:04d}"; out = []
        for li, (asset, qty, cat, price, kw) in enumerate(legs):
            self._id += 1
            e = Entry(id=self._id, block=block, tx=h, log_index=li, asset=asset, qty=D(qty), category=cat,
                      price=None if price is None else D(price), price_source=kw.pop("source", None if price is None else "fixture"),
                      label=kw.pop("label", None if price is None else "high"), tx_index=tx_index, **kw)
            self.rows.append(e); out.append(e)
        return out
def L(asset, qty, cat, price=None, **kw): return (asset, qty, cat, price, kw)

def marks(table):
    """Mark hook (Q-F stand-in for tests only): fixed synthetic prices per asset, independent of the block."""
    return lambda asset, block: None if asset not in table else Mark(D(table[asset]), "fixture_mark", "high")
