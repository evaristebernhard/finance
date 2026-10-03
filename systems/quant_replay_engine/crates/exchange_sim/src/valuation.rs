//! Shared mark-to-market calculation. Historical replay supplies the Runner ledger;
//! it never reconstructs that ledger from fills.
pub fn mark_account(cash: f64, position: f64, average: f64, mid: f64) -> (f64, f64, f64, f64) {
    let unrealized = (mid - average) * position;
    let equity = cash + position * mid;
    let notional = position.abs() * mid;
    let leverage = if equity.abs() > f64::EPSILON {
        notional / equity.abs()
    } else {
        f64::INFINITY
    };
    (unrealized, equity, notional, leverage)
}
