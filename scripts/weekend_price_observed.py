"""The weekend price effect measured on premia that were actually paid.

`weekend_price_impact.py` reconstructs every premium from the exchange's implied
volatility through Black-76. That is a modelled number, and the honest objection
to it is that a pricing effect stated in reconstructed prices is a statement
about the pricer as much as about the market. The tape carries the traded
premium itself, so the objection can be answered rather than conceded.

Four things, in increasing order of how little they assume:

1.  **Reconstruction accuracy.** Every trade's observed premium against the one
    Black-76 produces at the exchange's own implied volatility. If the two agree
    the reconstruction is a change of units, not an assumption.

2.  **The dollar figures restated on observed money.** Time value is directly
    observable -- premium paid minus forward intrinsic, both known per trade --
    so the aggregate effect can be stated against premium that changed hands
    with no pricer in the base at all. Only the counterfactual leg stays
    modelled, and it has to: the contract with the weekend taken out of it does
    not exist to be observed.

3.  **The effect itself, with no pricer anywhere.** Regressing log observed time
    value on the weekend fraction within a trade day, controlling for moneyness
    and maturity, measures the premium discount directly off traded prices. The
    pricer then has to predict that coefficient, which is a real test: it is
    free to be wrong and the reconstruction offers it no help.

4.  **Volatilities inverted from observed prices.** On a stratified subsample,
    Brent inversion of the traded premium, compared with the exchange's field
    and rerun through the whole calculation. Slow enough to be a subsample and
    important enough to be worth one.

Outputs o1-o5. Nothing here feeds the working paper; the write-up is the
observed-price section of paper/price_impact.md.
"""
from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd

from dbop import config, greeks

import weekend_price_impact as P

log = logging.getLogger("weekend_price_observed")

# Deribit's premium tick. Options that trade at one or two ticks carry a
# rounding error comparable to their own price, which is a real limit on what
# observed premia can resolve and is reported rather than filtered away.
TICK = {"BTC": 0.0005, "ETH": 0.0005, "SOL": 0.0001, "XRP": 0.0001}

# Controls for the model-free regression. A quadratic in log-moneyness and in
# log maturity, plus the call flag: enough to absorb the shape of a premium
# surface within a day without letting the weekend fraction proxy for maturity.
CONTROLS = ("logm", "logm2", "absm", "logT", "logT2", "is_call")

# Width of the log-moneyness band and the number of maturity bins that define a
# cell in the tight specification. Two percent in the strike is narrow enough
# that the premium surface is close to flat across a cell and wide enough that
# most cells still hold contracts of differing weekend exposure -- the trade-off
# the var_kept column reports.
MONEY_BIN = 0.02
MATURITY_BINS = 10


def derive(cur: str, d: pd.DataFrame) -> pd.DataFrame:
    """Observed premium, observed time value, and the reconstruction beside it.

    The premium is quoted in coin per unit of underlying on the inverse books
    and in dollars per unit on the linear ones, which is the one place the two
    conventions genuinely differ; `dbop.greeks.enrich` makes the same
    conversion and this follows it exactly.

    Time value is the premium less forward intrinsic. It is the part of the
    price that volatility sets, it is what the reconstruction should be judged
    on, and -- unlike the premium itself -- it is comparable between a call and
    the put at its strike.
    """
    F = d["F"].to_numpy()
    K = d["strike"].to_numpy()
    T = d["T_days"].to_numpy() / config.YEAR
    cp = np.where(d["is_call"].to_numpy() > 0, 1.0, -1.0)
    sig = np.sqrt(d["iv2"].to_numpy())

    obs = d["prem_quoted"].to_numpy()
    prem_obs = obs if config.LINEAR.get(cur, False) else obs * F

    out = pd.DataFrame(index=d.index)
    out["prem_obs"] = prem_obs
    out["prem_recon"] = greeks.price_usd(F, K, T, sig, cp)
    out["intrinsic"] = np.maximum(cp * (F - K), 0.0)
    out["tv_obs"] = prem_obs - out["intrinsic"].to_numpy()
    out["tv_recon"] = out["prem_recon"].to_numpy() - out["intrinsic"].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out["err_prem"] = out["prem_recon"] / out["prem_obs"] - 1.0
        out["err_tv"] = out["tv_recon"] / out["tv_obs"] - 1.0
    # A premium below forward intrinsic is not an arbitrage anyone traded: it is
    # the forward being slightly wrong for that instant, or a print that crossed
    # while the index moved. Counted, not silently dropped.
    out["tv_nonpositive"] = out["tv_obs"].to_numpy() <= 0
    out["at_tick"] = obs <= TICK.get(cur, 0.0) * 3 + 1e-12
    out["notional"] = d["size"].to_numpy() * F
    out["tv_obs_usd"] = out["tv_obs"].to_numpy() * d["size"].to_numpy()
    out["prem_obs_usd"] = prem_obs * d["size"].to_numpy()
    return out


def accuracy(cur: str, d: pd.DataFrame, o: pd.DataFrame,
             keys: list[str]) -> pd.DataFrame:
    """How close the reconstruction lands, by group.

    Quantiles rather than a mean: the error distribution has a tail of prints
    whose recorded volatility does not correspond to the recorded price at all
    -- late block legs, stale index stamps -- and a mean would report those
    rather than the typical trade.
    """
    g = pd.concat([d[keys], o], axis=1)
    rows = []
    for k, sub in g.groupby(keys, observed=True, dropna=True):
        ok = sub[~sub["tv_nonpositive"] & np.isfinite(sub["err_tv"])]
        key = k if isinstance(k, tuple) else (k,)
        rows.append({
            "currency": cur, **{c: v for c, v in zip(keys, key)},
            "n": len(sub),
            "share_tv_nonpositive": float(sub["tv_nonpositive"].mean()),
            "share_at_tick": float(sub["at_tick"].mean()),
            "err_tv_p10": float(ok["err_tv"].quantile(0.10)),
            "err_tv_med": float(ok["err_tv"].median()),
            "err_tv_p90": float(ok["err_tv"].quantile(0.90)),
            "share_within_1pct": float((ok["err_tv"].abs() < 0.01).mean()),
            "share_within_5pct": float((ok["err_tv"].abs() < 0.05).mean()),
            # Aggregate rather than typical: whether the *totals* the dollar
            # tables rest on are right, which is a weaker and more relevant
            # question than whether each print is.
            "tv_recon_over_obs": float(
                (ok["tv_recon"] * 1.0).sum() / (ok["tv_obs"] * 1.0).sum()),
        })
    return pd.DataFrame(rows)


def observed_impact(cur: str, d: pd.DataFrame, o: pd.DataFrame,
                    r: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """The dollar effect with observed time value as the base.

    The modelled ratio of the quoted price to its no-weekend counterfactual is
    applied to the premium that was actually paid, so the money in these columns
    is money that changed hands and only the counterfactual leg is modelled. The
    percentage columns are unchanged from the reconstructed tables by
    construction -- the ratio is the same -- and are carried so the two can be
    read side by side.
    """
    ratio = (r["tv_usd"] / r["tv_flat_usd"]).to_numpy()       # quoted / no-clock
    fair = (r["tv_usd"] / r["tv_fair_usd"]).to_numpy()        # quoted / realized
    g = pd.concat([d[keys], o[["tv_obs_usd", "prem_obs_usd", "tv_nonpositive"]]],
                  axis=1)
    g["ratio"], g["fair"] = ratio, fair
    g = g[~g["tv_nonpositive"] & np.isfinite(g["ratio"]) & (g["ratio"] > 0)
          & np.isfinite(g["fair"]) & (g["fair"] > 0)]
    rows = []
    for k, sub in g.groupby(keys, observed=True, dropna=True):
        obs = sub["tv_obs_usd"].to_numpy()
        flat = obs / sub["ratio"].to_numpy()      # what it would have cost
        fairv = obs / sub["fair"].to_numpy()      # what realized variance says
        key = k if isinstance(k, tuple) else (k,)
        rows.append({
            "currency": cur, **{c: v for c, v in zip(keys, key)},
            "n": len(sub),
            "tv_obs_usd_m": float(obs.sum()) / 1e6,
            "prem_obs_usd_m": float(sub["prem_obs_usd"].sum()) / 1e6,
            "tv_noclock_usd_m": float(flat.sum()) / 1e6,
            "discount_usd_m": float(flat.sum() - obs.sum()) / 1e6,
            "gap_usd_m": float(obs.sum() - fairv.sum()) / 1e6,
            "price_cut_pct": float(obs.sum() / flat.sum() - 1) * 100,
            "price_gap_pct": float(obs.sum() / fairv.sum() - 1) * 100,
        })
    return pd.DataFrame(rows)


# ------------------------------------------------ the pricer-free measurement
def _demean(y: np.ndarray, X: np.ndarray, key: np.ndarray):
    """Sweep out a fixed effect defined by `key`, in place.

    Group sums rather than a loop over groups: the tight specification puts
    millions of cells on the Bitcoin tape and a Python loop over them dominates
    the runtime of the whole script.
    """
    codes, uniq = pd.factorize(key, sort=False)
    n = len(uniq)
    counts = np.bincount(codes, minlength=n).astype("float64")
    y -= (np.bincount(codes, weights=y, minlength=n) / counts)[codes]
    for j in range(X.shape[1]):
        X[:, j] -= (np.bincount(codes, weights=X[:, j], minlength=n)
                    / counts)[codes]
    return y, X, n


def fe_ols(y: np.ndarray, X: np.ndarray, cell: np.ndarray,
           cluster: np.ndarray) -> dict:
    """OLS with a fixed effect swept out and standard errors clustered on days.

    The fixed effect and the cluster are separate because they have to be. The
    tightest sensible control here is a cell of trades that printed on the same
    day, at the same strike, with the same maturity -- but residuals are
    correlated across every cell within a day, so inference still has to be
    clustered at the day.

    Also returns the share of the weekend fraction's variance that survives the
    fixed effect. That number is the honest measure of how much identifying
    variation a specification has left itself, and in the far wing at fine cells
    it is what says the estimate should not be believed.
    """
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    y, X, cell, cluster = y[ok], X[ok], cell[ok], cluster[ok]
    if len(y) < 500 or len(np.unique(cluster)) < 30:
        return {}
    var_raw = float(np.var(X[:, 0]))
    y, X, n_cells = _demean(y.copy(), X.copy(), cell)
    kept = float(np.var(X[:, 0]) / var_raw) if var_raw > 0 else np.nan

    order = np.argsort(cluster, kind="stable")
    y, X, day = y[order], X[order], cluster[order]
    _, starts = np.unique(day, return_index=True)
    ends = list(starts[1:]) + [len(y)]
    XtX = X.T @ X
    try:
        beta = np.linalg.solve(XtX, X.T @ y)
    except np.linalg.LinAlgError:
        return {}
    resid = y - X @ beta
    meat = np.zeros((X.shape[1], X.shape[1]))
    for a, b in zip(starts, ends):
        s = X[a:b].T @ resid[a:b]
        meat += np.outer(s, s)
    inv = np.linalg.inv(XtX)
    n_g = len(starts)
    cov = inv @ meat @ inv * (n_g / max(n_g - 1, 1))
    se = float(np.sqrt(np.diag(cov))[0])
    return {"n": int(len(y)), "n_days": int(n_g), "n_cells": int(n_cells),
            "var_kept": kept, "beta": float(beta[0]), "se": se,
            "t": float(beta[0] / se) if se > 0 else np.nan,
            "_w": X[:, 0] ** 2, "_ok": ok, "_order": order}


# Distance from the money in day-level standard deviations. Bucketing on delta
# is what section 7 does and it is the wrong thing here: delta is a function of
# the contract's own volatility, which is a function of its weekend fraction, so
# conditioning on a delta bucket conditions on the very thing being measured.
# Standardizing against the *day's* at-the-money level instead gives a distance
# that no single contract's weekend exposure can move.
Z_BINS = (0.0, 0.5, 1.0, 2.0, np.inf)
Z_LABELS = ("at the money", "near", "wing", "far wing")


def fixed_bucket(d: pd.DataFrame) -> pd.Series:
    """Moneyness buckets built on a scale the weekend fraction cannot move."""
    sig = np.sqrt(d["iv2"].to_numpy())
    atm = pd.Series(np.where(d["atmness"].to_numpy() >= 0.35, sig, np.nan),
                    index=d.index).groupby(d["date"]).transform("mean")
    z = np.abs(d["logm"].to_numpy()) / (
        atm.to_numpy() * np.sqrt(d["T_days"].to_numpy() / config.YEAR))
    return pd.cut(z, Z_BINS, labels=list(Z_LABELS), right=False)


def premium_regression(cur: str, d: pd.DataFrame, o: pd.DataFrame,
                       R: float) -> pd.DataFrame:
    """Log observed time value on the weekend fraction, by moneyness bucket.

    No pricer touches the outcome. The coefficient is the proportional premium
    discount per unit of weekend exposure, read straight off traded prices.

    The comparison that settles the question is the same regression run on the
    reconstructed premium and the difference between the two coefficients, which
    is estimated directly by regressing the log ratio of the two price series --
    so it carries its own clustered standard error and does not require the two
    fits to be independent. A difference of zero says observed and reconstructed
    prices carry the same weekend effect, which is the only thing the companion
    note needs from them.

    The local-derivative prediction is reported alongside,

        d log C / d w = -elasticity * (1 - R) / (2 * f),

    but it is not the test. A regression linear in the weekend fraction recovers
    a chord, and log premium is strongly convex in that fraction away from the
    money, so the two quantities part company in the wings even when the prices
    were generated by the pricer itself -- which is what
    tests/test_price_observed.py pins. Reading the wing rows of `predicted` as a
    claim about the market would be reading the estimator's own linearization.
    """
    x = pd.DataFrame(index=d.index)
    x["logm"] = d["logm"]
    x["logm2"] = d["logm"] ** 2
    x["absm"] = d["logm"].abs()
    x["logT"] = d["logT"]
    x["logT2"] = d["logT"] ** 2
    x["is_call"] = d["is_call"]
    x["wknd_frac"] = d["wknd_frac"]
    x["bucket"] = fixed_bucket(d)
    x["at_tick"] = o["at_tick"]
    x["day"] = d["date"].astype("int64")
    # The tight control: same day, same strike to within a two percent band,
    # same maturity decile. Binning on the strike rather than on standardized
    # moneyness is not cosmetic -- the pricer's elasticity is a derivative at a
    # fixed strike, and conditioning on standardized moneyness instead lets the
    # strike move with the clock and measures a different derivative entirely.
    # Built as integer codes rather than concatenated strings: the tape is
    # millions of rows and a string key for each is gigabytes of nothing.
    mb = np.floor(d["logm"].to_numpy() / MONEY_BIN).astype("int64")
    tb = pd.qcut(d["logT"], MATURITY_BINS, labels=False,
                 duplicates="drop").to_numpy().astype("int64")
    day = pd.factorize(d["date"].to_numpy())[0].astype("int64")
    span = int(mb.max() - mb.min() + 1)
    x["cell"] = (day * MATURITY_BINS + tb) * span + (mb - mb.min())
    with np.errstate(divide="ignore", invalid="ignore"):
        x["y"] = np.log(o["tv_obs"].to_numpy() / d["F"].to_numpy())
        x["y_recon"] = np.log(o["tv_recon"].to_numpy() / d["F"].to_numpy())
        x["y_diff"] = x["y"] - x["y_recon"]
    x = x[~o["tv_nonpositive"].to_numpy() & np.isfinite(x["y"].to_numpy())
          & np.isfinite(x["y_recon"].to_numpy())]

    # The model's own prediction for the same coefficient, per trade.
    K = np.exp(d["logm"].to_numpy())
    T = d["T_days"].to_numpy() / config.YEAR
    otm = np.where(K >= 1.0, 1.0, -1.0)
    sig = np.sqrt(d["iv2"].to_numpy())
    f = P.damp(d["wknd_frac"].to_numpy(), R)
    el = P.elasticity(1.0, K, T, sig, otm)
    x["pred"] = pd.Series(-el * (1.0 - R) / (2.0 * f),
                          index=d.index).reindex(x.index).to_numpy()

    rows = []
    # The third specification exists because of what the second finds. In the
    # far wing the observed discount comes in at roughly half what the pricer
    # predicts, and the obvious suspect is the premium tick: an option worth
    # less than one tick cannot be quoted any cheaper, so the clock's effect on
    # it is truncated by the venue's own price grid rather than by anything
    # economic. Dropping the prints sitting on that floor is the test.
    specs = (("day FE, polynomial controls", "day", True, False),
             ("day x strike x maturity cell", "cell", False, False),
             ("cell, off-tick prints only", "cell", False, True))
    for name, fe, poly, drop_tick in specs:
        for lab in ("all",) + Z_LABELS:
            sub = x if lab == "all" else x[x["bucket"] == lab]
            if drop_tick:
                sub = sub[~sub["at_tick"].to_numpy()]
            if sub.empty:
                continue
            cols = CONTROLS if poly else ("logm", "logT")
            X = np.column_stack([sub["wknd_frac"].to_numpy(dtype="float64")]
                                + [sub[c].to_numpy(dtype="float64")
                                   for c in cols])
            res = fe_ols(sub["y"].to_numpy(dtype="float64"), X,
                         sub[fe].to_numpy(), sub["day"].to_numpy())
            if not res:
                continue
            rec = fe_ols(sub["y_recon"].to_numpy(dtype="float64"), X.copy(),
                         sub[fe].to_numpy(), sub["day"].to_numpy())
            dif = fe_ols(sub["y_diff"].to_numpy(dtype="float64"), X.copy(),
                         sub[fe].to_numpy(), sub["day"].to_numpy())
            for r_ in (rec, dif):
                for k_ in ("_w", "_ok", "_order"):
                    r_.pop(k_, None)
            # The coefficient is a variance-weighted average of the individual
            # derivatives, so the prediction it should be compared against has
            # to carry the same weights. An unweighted mean of the per-trade
            # prediction is a different quantity and, in the wings where the
            # elasticity has a long right tail, a materially different number.
            wt = res.pop("_w")
            ok, order = res.pop("_ok"), res.pop("_order")
            pr = sub["pred"].to_numpy()[ok][order]
            good = np.isfinite(pr)
            pred = float(np.sum(wt[good] * pr[good]) / np.sum(wt[good]))
            rows.append({"currency": cur, "spec": name, "bucket": lab,
                         **res,
                         "beta_recon": rec.get("beta", np.nan),
                         "beta_diff": dif.get("beta", np.nan),
                         "se_diff": dif.get("se", np.nan),
                         "t_diff": dif.get("t", np.nan),
                         "predicted": pred,
                         "share_at_tick": float(sub["at_tick"].mean()),
                         "t_vs_predicted": float((res["beta"] - pred)
                                                 / res["se"])
                         if res["se"] > 0 else np.nan})
    return pd.DataFrame(rows)


# ------------------------------------------------------ inverting the premium
def inversion(cur: str, d: pd.DataFrame, o: pd.DataFrame, R: float,
              per_year: int = 4000, seed: int = 0) -> pd.DataFrame:
    """Volatilities recovered from traded premia, on a stratified subsample.

    Brent is scalar and the tape is not, so this is a sample: up to `per_year`
    trades a year, drawn at random within the year so the draw does not track
    liquidity. The point is not another accuracy check on the volatility field
    -- section 2.2 of the paper does that -- but to run the price effect itself
    on volatilities that owe the exchange nothing.
    """
    rng = np.random.default_rng(seed)
    good = (~o["tv_nonpositive"].to_numpy()) & np.isfinite(o["tv_obs"].to_numpy())
    idx = d.index[good]
    year = d.loc[idx, "date"].dt.year.to_numpy()
    take = []
    for y in np.unique(year):
        pool = idx[year == y]
        take.append(rng.choice(pool, size=min(per_year, len(pool)),
                               replace=False))
    take = np.concatenate(take)
    s = d.loc[take]
    F = s["F"].to_numpy()
    K = s["strike"].to_numpy()
    T = s["T_days"].to_numpy() / config.YEAR
    cp = np.where(s["is_call"].to_numpy() > 0, 1.0, -1.0)
    sig_inv = greeks.implied_vol(o.loc[take, "prem_obs"].to_numpy(), F, K, T, cp)
    sig_ex = np.sqrt(s["iv2"].to_numpy())

    ok = np.isfinite(sig_inv) & np.isfinite(sig_ex) & (sig_ex > 0)
    w = s["wknd_frac"].to_numpy()
    otm = np.where(K / F >= 1.0, 1.0, -1.0)
    Kf = K / F

    def effect(sig):
        f = P.damp(w, R)
        flat = sig / np.sqrt(f)
        c_q = greeks.price_usd(1.0, Kf, T, sig, otm)
        c_f = greeks.price_usd(1.0, Kf, T, flat, otm)
        num = c_q * s["size"].to_numpy() * F
        den = c_f * s["size"].to_numpy() * F
        m = np.isfinite(num) & np.isfinite(den) & (den > 0) & ok
        return float(num[m].sum() / den[m].sum() - 1) * 100

    return pd.DataFrame([{
        "currency": cur, "n": int(ok.sum()),
        "iv_exchange_mean": float(np.mean(sig_ex[ok])),
        "iv_inverted_mean": float(np.mean(sig_inv[ok])),
        "iv_diff_med_pts": float(np.median(sig_inv[ok] - sig_ex[ok])) * 100,
        "iv_diff_p10_pts": float(np.quantile(sig_inv[ok] - sig_ex[ok], 0.1)) * 100,
        "iv_diff_p90_pts": float(np.quantile(sig_inv[ok] - sig_ex[ok], 0.9)) * 100,
        "share_inverted": float(np.isfinite(sig_inv).mean()),
        "price_cut_pct_exchange_iv": effect(sig_ex),
        "price_cut_pct_inverted_iv": effect(sig_inv),
    }])


# --------------------------------------------------------------------- driver
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--currency", default=None)
    ap.add_argument("--per-year", type=int, default=4000,
                    help="inversion subsample size per year per book")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    curs = [a.currency] if a.currency else list(config.CURRENCIES)
    rat = P.ratios()
    acc, imp, reg, inv, acc_b = [], [], [], [], []
    for c in curs:
        log.info("loading %s", c)
        d = P.load(c, extra=("prem_quoted", "strike"))
        d["year"] = d["date"].dt.year
        d["_all"] = "all"
        R = float(rat.loc[c, "implied_ratio"])
        R_real = float(rat.loc[c, "variance_ratio"])
        o = derive(c, d)
        r = P.reprice(d, np.full(len(d), R), np.full(len(d), R_real))

        acc.append(accuracy(c, d, o, ["_all"]))
        acc_b.append(accuracy(c, d, o, ["bucket"]))
        imp.append(observed_impact(c, d, o, r, ["_all"]))
        imp.append(observed_impact(c, d, o, r, ["bucket"]))
        imp.append(observed_impact(c, d, o, r, ["year"]))
        del r
        log.info("%s: regression on observed premia", c)
        reg.append(premium_regression(c, d, o, R))
        log.info("%s: inverting a subsample", c)
        inv.append(inversion(c, d, o, R, per_year=a.per_year))
        del d, o

    out = {
        "o1_premium_reconstruction": pd.concat(acc, ignore_index=True),
        "o2_premium_reconstruction_by_moneyness": pd.concat(acc_b,
                                                            ignore_index=True),
        "o3_observed_impact": pd.concat(imp, ignore_index=True),
        "o4_observed_premium_regression": pd.concat(reg, ignore_index=True),
        "o5_inverted_iv": pd.concat(inv, ignore_index=True),
    }
    for name, t in out.items():
        t.to_csv(config.TABLES / f"{name}.csv", index=False)

    fmt = lambda x: f"{x:9.4f}"
    print("\n=== reconstruction vs observed time value ===")
    print(out["o1_premium_reconstruction"][
        ["currency", "n", "err_tv_med", "share_within_1pct",
         "share_within_5pct", "tv_recon_over_obs", "share_tv_nonpositive",
         "share_at_tick"]].to_string(index=False, float_format=fmt))
    print("\n=== effect on observed premium ===")
    print(out["o3_observed_impact"].query("_all == 'all'")[
        ["currency", "tv_obs_usd_m", "prem_obs_usd_m", "discount_usd_m",
         "gap_usd_m", "price_cut_pct", "price_gap_pct"]]
        .to_string(index=False, float_format=fmt))
    print("\n=== d log(observed time value) / d weekend fraction ===")
    print(out["o4_observed_premium_regression"][
        ["currency", "spec", "bucket", "n", "var_kept", "beta", "se",
         "beta_recon", "beta_diff", "se_diff", "t_diff", "predicted",
         "share_at_tick"]]
        .to_string(index=False, float_format=fmt))
    print("\n=== volatilities inverted from traded premia ===")
    print(out["o5_inverted_iv"].to_string(index=False, float_format=fmt))
    for name in out:
        print(f"-> {config.TABLES / (name + '.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
