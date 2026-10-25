"""Pool discovery check (verify/p3_pools.py). Root causes of the missed GLTR/GHST pool 0xa83b31d7…: (1) 2026-10-17, the GLTR address
in the script had 41 hex digits ("…219aafbc…"); (2) 2026-10-23, an ad-hoc zsh re-check did not word-split `set -- $pair`, so the quote
token was empty (encoded as 0x0). Both returned getPool = 0x0 silently. The script now rejects any address that is not 20 non-zero bytes."""
import importlib.util, os, re, unittest
from cryptopnl import config
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("p3_pools", os.path.join(ROOT, "verify", "p3_pools.py")); pp = importlib.util.module_from_spec(spec); spec.loader.exec_module(pp)
GLTR = "0x4d140ce792bedc430498c2d219afbc33e2992c9d"; GHST = "0xcd2f22236dd9dfe2356d7c543161d4d260fd9bcb"
ADDR = re.compile(r"^0x[0-9a-f]{40}$")

class PoolCheck(unittest.TestCase):
    def test_gltr_ghst_aerodrome_v2_volatile_calldata(self):
        c = {(k, str(p)): (f, d) for k, p, f, d in pp.calls_for(GLTR, GHST)}
        f, d = c[("aeroV2", "False")]
        self.assertEqual(f, "0x420dd381b31aef6683db6b902084cb0ffece40da")
        self.assertEqual(d, "0x79bc57d5" + "0" * 24 + GLTR[2:] + "0" * 24 + GHST[2:] + "0" * 64)   # getPool(GLTR, GHST, false)
        self.assertEqual(len(d), 2 + 8 + 3 * 64)
    def test_bad_addresses_rejected(self):
        for bad in ("0x4d140ce792bedc430498c2d219aafbc33e2992c9d", "", "0x", "0x" + "0" * 40, "cd2f22236dd9dfe2356d7c543161d4d260fd9bcb"):
            with self.subTest(bad=bad), self.assertRaises(ValueError): pp.calls_for(GLTR, bad)
    def test_every_configured_address_is_20_bytes(self):
        addrs = set(pp.T.values()) | {pp.USDC, pp.UNI, pp.AERO, *pp.CL}
        for ch, toks in config.TOKENS.items(): addrs |= set(toks)
        for ch, m in config.PRICE_POOLS.items():
            for a, pools in m.items(): addrs.add(a); addrs |= {p for _, p, _ in pools} | {q for _, _, q in pools}
        for d in (config.THIN_POOL_ASSETS, config.THIN_ONLY_ASSETS, config.NO_PRICE_SOURCE, config.DEV_GATED_ASSETS, config.NUMERAIRE, config.WETH):
            for v in d.values(): addrs |= set(v) if isinstance(v, (set, list)) else {v}
        for ch, s in config.ALLOWLIST.items(): addrs |= set(s)
        bad = sorted(a for a in addrs if not ADDR.match(a)); self.assertEqual(bad, [])
    def test_gltr_pool_in_price_config(self):
        self.assertEqual(config.PRICE_POOLS[8453][GLTR], [("v2", "0xa83b31d701633b8edcfba55b93ddbc202d8a4621", GHST)])

if __name__ == "__main__": unittest.main()
