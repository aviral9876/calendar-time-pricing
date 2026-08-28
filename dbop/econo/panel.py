"""Cross-sectional test: which parts of the surface are dealers short?

GPP's second prediction, and the sharper one. With day fixed effects absorbing
the market-wide level of implied vol, identification comes entirely from
variation across buckets on the same day: the parts of the surface where end
users are net long, and dealers therefore net short, should be the parts that
trade rich relative to the rest of that day's surface.

Because the same day and the same bucket both induce correlation, the default
inference is two-way clustering; Driscoll-Kraay is reported alongside because
it is robust to cross-sectional dependence of arbitrary form, which a surface
panel certainly has (all buckets load on one vol factor).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS


def _entity_time(df: pd.DataFrame, entity: str = "bucket",
                 time: str = "date") -> pd.DataFrame:
    d = df.copy()
    d[time] = pd.to_datetime(d[time])
    return d.set_index([entity, time])


def cross_section(buckets: pd.DataFrame, y: str = "exp_bucket",
                  demand: str = "dealer_vega_sc_lag",
                  controls: tuple[str, ...] = (),
                  entity_effects: bool = True, time_effects: bool = True,
                  cov: str = "clustered") -> dict:
    """Panel regression of bucket expensiveness on lagged dealer inventory.

    ``demand`` enters negated, so a positive coefficient means richer options
    where dealers are shorter vol.
    """
    d = buckets.copy()
    d["neg_inv"] = -d[demand]
    xs = ["neg_inv"] + [c for c in controls if c in d.columns]

    cols = [y] + xs + ["bucket", "date"]
    d = d[cols].replace([np.inf, -np.inf], np.nan).dropna()
    if d["bucket"].nunique() < 3 or len(d) < 200:
        return {"n": len(d), "error": "insufficient panel"}

    pdata = _entity_time(d)
    mod = PanelOLS(pdata[y], pdata[xs], entity_effects=entity_effects,
                   time_effects=time_effects, drop_absorbed=True,
                   check_rank=False)

    if cov == "driscoll-kraay":
        res = mod.fit(cov_type="kernel", kernel="bartlett", bandwidth=20)
    elif cov == "clustered":
        res = mod.fit(cov_type="clustered", cluster_entity=True,
                      cluster_time=True)
    else:
        res = mod.fit(cov_type=cov)

    # Raw coefficients are not comparable across currencies. The normalized
    # demand variable is not scale-free in practice -- its standard deviation
    # is roughly eighteen times larger for ETH than BTC -- so a raw beta that
    # looks twenty times smaller may describe the same economic effect. Report
    # the effect of a one-standard-deviation move in demand, in vol points.
    sd = float(d["neg_inv"].std())
    beta = float(res.params.get("neg_inv", np.nan))
    return {
        "n": int(res.nobs),
        "n_entities": int(d["bucket"].nunique()),
        "r2_within": float(res.rsquared_within),
        "params": res.params.to_dict(),
        "tstats": res.tstats.to_dict(),
        "pvalues": res.pvalues.to_dict(),
        "sd_demand": sd,
        "beta_per_sd": beta * sd,
        "beta_per_sd_volpts": beta * sd * 100,
        "cov": cov,
        "res": res,
    }


def robustness_suite(buckets: pd.DataFrame, y: str = "exp_bucket") -> pd.DataFrame:
    """The specification grid reported in the paper's robustness table."""
    specs = {
        "vega, two-way cluster": dict(demand="dealer_vega_sc_lag",
                                      cov="clustered"),
        "vega, Driscoll-Kraay": dict(demand="dealer_vega_sc_lag",
                                     cov="driscoll-kraay"),
        "gamma, two-way cluster": dict(demand="dealer_gamma_sc_lag",
                                       cov="clustered"),
        "vega, no time FE": dict(demand="dealer_vega_sc_lag", cov="clustered",
                                 time_effects=False),
        "vega, no bucket FE": dict(demand="dealer_vega_sc_lag", cov="clustered",
                                   entity_effects=False),
    }
    rows = []
    for label, kw in specs.items():
        r = cross_section(buckets, y=y, **kw)
        rows.append({
            "spec": label,
            "n": r.get("n", 0),
            "beta": r.get("params", {}).get("neg_inv", np.nan),
            "t": r.get("tstats", {}).get("neg_inv", np.nan),
            "p": r.get("pvalues", {}).get("neg_inv", np.nan),
            "vol_pts_per_sd": r.get("beta_per_sd_volpts", np.nan),
            "r2_within": r.get("r2_within", np.nan),
        })
    return pd.DataFrame(rows)


def by_subsample(buckets: pd.DataFrame, breaks: dict,
                 y: str = "exp_bucket") -> pd.DataFrame:
    """Estimate the demand elasticity separately in each regime.

    The paper's question is whether the effect compresses as institutional
    capital enters the market, so the subsample split is substantive, not just
    a robustness check.
    """
    d = buckets.copy()
    d["date"] = pd.to_datetime(d["date"])
    edges = [pd.Timestamp("2000-01-01", tz="UTC")] + \
        [pd.Timestamp(v, tz="UTC") for v in sorted(breaks.values())] + \
        [pd.Timestamp("2100-01-01", tz="UTC")]
    labels = ["pre-" + str(sorted(breaks.values())[0])] + \
        [f"from {v}" for v in sorted(breaks.values())]

    rows = []
    for lo, hi, label in zip(edges[:-1], edges[1:], labels):
        sub = d[(d["date"] >= lo) & (d["date"] < hi)]
        if len(sub) < 500:
            continue
        r = cross_section(sub, y=y)
        rows.append({
            "subsample": label,
            "start": sub["date"].min().date(),
            "end": sub["date"].max().date(),
            "n": r.get("n", 0),
            "beta": r.get("params", {}).get("neg_inv", np.nan),
            "t": r.get("tstats", {}).get("neg_inv", np.nan),
        })
    return pd.DataFrame(rows)
