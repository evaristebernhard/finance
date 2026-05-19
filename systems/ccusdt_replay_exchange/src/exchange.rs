use anyhow::{Result, bail};

use crate::types::{
    AccountView, ExchangeConfig, ExchangeSnapshot, Fill, Liquidity, MarketFrame, NewOrder, Order,
    OrderKind, OrderStatus, Side, TimeInForce,
};

#[derive(Clone, Debug)]
struct AccountLedger {
    initial_cash: f64,
    cash: f64,
    position_qty: f64,
    avg_entry_price: f64,
    realized_pnl: f64,
    fees_paid: f64,
}

impl AccountLedger {
    fn new(initial_cash: f64) -> Self {
        Self {
            initial_cash,
            cash: initial_cash,
            position_qty: 0.0,
            avg_entry_price: 0.0,
            realized_pnl: 0.0,
            fees_paid: 0.0,
        }
    }

    fn view(&self, mid: f64) -> AccountView {
        let unrealized_pnl = match self.position_qty.total_cmp(&0.0) {
            std::cmp::Ordering::Greater => (mid - self.avg_entry_price) * self.position_qty,
            std::cmp::Ordering::Less => (self.avg_entry_price - mid) * self.position_qty.abs(),
            std::cmp::Ordering::Equal => 0.0,
        };
        let equity = self.cash + self.position_qty * mid;
        let notional = self.position_qty.abs() * mid;
        let leverage = if equity.abs() > f64::EPSILON {
            notional / equity.abs()
        } else {
            f64::INFINITY
        };
        AccountView {
            initial_cash: self.initial_cash,
            cash: self.cash,
            position_qty: self.position_qty,
            avg_entry_price: self.avg_entry_price,
            realized_pnl: self.realized_pnl,
            unrealized_pnl,
            fees_paid: self.fees_paid,
            equity,
            notional,
            leverage,
        }
    }

    fn apply_fill(&mut self, side: Side, qty: f64, price: f64, fee: f64) {
        let signed_qty = side.signed_qty(qty);
        let old_pos = self.position_qty;
        let old_avg = self.avg_entry_price;

        self.cash -= signed_qty * price;
        self.cash -= fee;
        self.fees_paid += fee;

        if old_pos == 0.0 || old_pos.signum() == signed_qty.signum() {
            let new_abs = old_pos.abs() + signed_qty.abs();
            self.position_qty = old_pos + signed_qty;
            self.avg_entry_price = if new_abs > 0.0 {
                (old_avg * old_pos.abs() + price * signed_qty.abs()) / new_abs
            } else {
                0.0
            };
            return;
        }

        let closing_qty = old_pos.abs().min(signed_qty.abs());
        if old_pos > 0.0 {
            self.realized_pnl += (price - old_avg) * closing_qty;
        } else {
            self.realized_pnl += (old_avg - price) * closing_qty;
        }

        let new_pos = old_pos + signed_qty;
        self.position_qty = new_pos;
        if new_pos == 0.0 {
            self.avg_entry_price = 0.0;
        } else if new_pos.signum() == old_pos.signum() {
            self.avg_entry_price = old_avg;
        } else {
            self.avg_entry_price = price;
        }
    }
}

#[derive(Clone, Debug)]
pub struct PaperExchange {
    config: ExchangeConfig,
    frames: Vec<MarketFrame>,
    cursor: usize,
    account: AccountLedger,
    orders: Vec<Order>,
    fills: Vec<Fill>,
    next_order_id: u64,
    next_fill_id: u64,
}

impl PaperExchange {
    pub fn new(config: ExchangeConfig, frames: Vec<MarketFrame>) -> Result<Self> {
        if config.starting_cash <= 0.0 {
            bail!("starting_cash must be positive");
        }
        if config.fee_bps < 0.0 {
            bail!("fee_bps must be >= 0");
        }
        if config.max_leverage <= 0.0 {
            bail!("max_leverage must be positive");
        }
        if frames.is_empty() {
            bail!("paper exchange needs at least one market frame");
        }
        Ok(Self {
            account: AccountLedger::new(config.starting_cash),
            config,
            frames,
            cursor: 0,
            orders: Vec::new(),
            fills: Vec::new(),
            next_order_id: 1,
            next_fill_id: 1,
        })
    }

    pub fn reset(&mut self) {
        self.cursor = 0;
        self.account = AccountLedger::new(self.config.starting_cash);
        self.orders.clear();
        self.fills.clear();
        self.next_order_id = 1;
        self.next_fill_id = 1;
    }

    pub fn current_frame(&self) -> &MarketFrame {
        &self.frames[self.cursor]
    }

    pub fn snapshot(&self) -> ExchangeSnapshot {
        let frame = self.current_frame().clone();
        ExchangeSnapshot {
            config: self.config.clone(),
            cursor: self.cursor,
            frame_count: self.frames.len(),
            account: self.account.view(frame.mid),
            current_frame: frame,
            open_orders: self
                .orders
                .iter()
                .filter(|order| order.status == OrderStatus::Open)
                .cloned()
                .collect(),
            order_count: self.orders.len(),
            fill_count: self.fills.len(),
        }
    }

    pub fn orders(&self) -> &[Order] {
        &self.orders
    }

    pub fn fills(&self) -> &[Fill] {
        &self.fills
    }

    pub fn place_order(&mut self, request: NewOrder) -> Result<Order> {
        self.validate_new_order(&request)?;
        let seq = self.current_frame().seq;
        let id = self.next_order_id;
        self.next_order_id += 1;

        let mut order = Order {
            id,
            client_order_id: request.client_order_id.clone(),
            side: request.side,
            kind: request.kind,
            qty: request.qty,
            remaining_qty: request.qty,
            filled_qty: 0.0,
            limit_price: request.limit_price,
            tif: request.tif,
            reduce_only: request.reduce_only,
            status: OrderStatus::Open,
            reject_reason: None,
            avg_fill_price: None,
            created_seq: seq,
            updated_seq: seq,
        };

        if let Err(reason) = self.check_risk(&order) {
            order.status = OrderStatus::Rejected;
            order.reject_reason = Some(reason);
            order.updated_seq = seq;
            self.orders.push(order.clone());
            return Ok(order);
        }

        self.orders.push(order);
        let index = self.orders.len() - 1;
        self.try_match_order(index);
        if self.orders[index].status == OrderStatus::Open
            && self.orders[index].tif == TimeInForce::Ioc
        {
            self.orders[index].status = OrderStatus::Canceled;
            self.orders[index].updated_seq = seq;
        }
        Ok(self.orders[index].clone())
    }

    pub fn cancel_order(&mut self, order_id: u64) -> Option<Order> {
        let seq = self.current_frame().seq;
        let order = self
            .orders
            .iter_mut()
            .find(|order| order.id == order_id && order.status == OrderStatus::Open)?;
        order.status = OrderStatus::Canceled;
        order.updated_seq = seq;
        Some(order.clone())
    }

    pub fn step(&mut self, frames: usize) -> ExchangeSnapshot {
        for _ in 0..frames {
            if self.cursor + 1 >= self.frames.len() {
                break;
            }
            self.cursor += 1;
            self.match_open_orders();
        }
        self.snapshot()
    }

    fn validate_new_order(&self, request: &NewOrder) -> Result<()> {
        if request.qty <= 0.0 || !request.qty.is_finite() {
            bail!("qty must be positive and finite");
        }
        match request.kind {
            OrderKind::Market => {
                if request.limit_price.is_some() {
                    bail!("market order must not include limit_price");
                }
            }
            OrderKind::Limit => {
                let limit = request
                    .limit_price
                    .ok_or_else(|| anyhow::anyhow!("limit order needs limit_price"))?;
                if limit <= 0.0 || !limit.is_finite() {
                    bail!("limit_price must be positive and finite");
                }
            }
        }
        Ok(())
    }

    fn check_risk(&self, order: &Order) -> std::result::Result<(), String> {
        let frame = self.current_frame();
        let mark = match order.side {
            Side::Buy => frame.ask,
            Side::Sell => frame.bid,
        };
        let current_view = self.account.view(frame.mid);
        if current_view.equity <= 0.0 {
            return Err("equity is non-positive".to_string());
        }

        let signed_qty = order.side.signed_qty(order.remaining_qty);
        let projected_pos = self.account.position_qty + signed_qty;
        if order.reduce_only && projected_pos.abs() >= self.account.position_qty.abs() {
            return Err("reduce_only order would not reduce exposure".to_string());
        }

        let projected_notional = projected_pos.abs() * mark;
        let max_notional = current_view.equity * self.config.max_leverage;
        if projected_notional > max_notional + 1e-9 {
            return Err(format!(
                "projected leverage {:.4} exceeds max {:.4}",
                projected_notional / current_view.equity,
                self.config.max_leverage
            ));
        }
        Ok(())
    }

    fn match_open_orders(&mut self) {
        let len = self.orders.len();
        for index in 0..len {
            if self.orders[index].status == OrderStatus::Open {
                self.try_match_order(index);
            }
        }
    }

    fn try_match_order(&mut self, index: usize) {
        if self.orders[index].remaining_qty <= 0.0 || self.orders[index].status != OrderStatus::Open
        {
            return;
        }

        let frame = self.current_frame().clone();
        let Some((price, liquidity)) = fill_price(&self.orders[index], &frame) else {
            return;
        };

        let qty = self.orders[index].remaining_qty;
        let fee = price * qty * self.config.fee_bps / 10_000.0;
        self.account
            .apply_fill(self.orders[index].side, qty, price, fee);

        let old_filled = self.orders[index].filled_qty;
        self.orders[index].filled_qty += qty;
        self.orders[index].remaining_qty = 0.0;
        self.orders[index].status = OrderStatus::Filled;
        self.orders[index].updated_seq = frame.seq;
        self.orders[index].avg_fill_price = Some(match self.orders[index].avg_fill_price {
            Some(avg) if old_filled > 0.0 => (avg * old_filled + price * qty) / (old_filled + qty),
            _ => price,
        });

        self.fills.push(Fill {
            id: self.next_fill_id,
            order_id: self.orders[index].id,
            side: self.orders[index].side,
            qty,
            price,
            fee,
            liquidity,
            seq: frame.seq,
            ts: frame.ts,
        });
        self.next_fill_id += 1;
    }
}

fn fill_price(order: &Order, frame: &MarketFrame) -> Option<(f64, Liquidity)> {
    match order.kind {
        OrderKind::Market => Some(match order.side {
            Side::Buy => (frame.ask, Liquidity::Taker),
            Side::Sell => (frame.bid, Liquidity::Taker),
        }),
        OrderKind::Limit => {
            let limit = order.limit_price?;
            let is_new = order.created_seq == frame.seq;
            match order.side {
                Side::Buy if frame.ask <= limit => {
                    let price = if is_new { frame.ask } else { limit };
                    Some((
                        price,
                        if is_new {
                            Liquidity::Taker
                        } else {
                            Liquidity::Maker
                        },
                    ))
                }
                Side::Sell if frame.bid >= limit => {
                    let price = if is_new { frame.bid } else { limit };
                    Some((
                        price,
                        if is_new {
                            Liquidity::Taker
                        } else {
                            Liquidity::Maker
                        },
                    ))
                }
                _ => None,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frames() -> Vec<MarketFrame> {
        vec![
            MarketFrame::new(0, "t0", 99.0, 101.0).unwrap(),
            MarketFrame::new(1, "t1", 98.0, 100.0).unwrap(),
            MarketFrame::new(2, "t2", 101.0, 103.0).unwrap(),
        ]
    }

    fn exchange() -> PaperExchange {
        PaperExchange::new(ExchangeConfig::default(), frames()).unwrap()
    }

    #[test]
    fn market_buy_fills_at_ask() {
        let mut exchange = exchange();
        let order = exchange
            .place_order(NewOrder {
                side: Side::Buy,
                kind: OrderKind::Market,
                qty: 2.0,
                limit_price: None,
                tif: TimeInForce::Ioc,
                reduce_only: false,
                client_order_id: None,
            })
            .unwrap();
        assert_eq!(order.status, OrderStatus::Filled);
        assert_eq!(exchange.fills()[0].price, 101.0);
        assert_eq!(exchange.snapshot().account.position_qty, 2.0);
    }

    #[test]
    fn resting_limit_fills_after_quote_crosses() {
        let mut exchange = exchange();
        let order = exchange
            .place_order(NewOrder {
                side: Side::Buy,
                kind: OrderKind::Limit,
                qty: 1.0,
                limit_price: Some(100.0),
                tif: TimeInForce::Gtc,
                reduce_only: false,
                client_order_id: None,
            })
            .unwrap();
        assert_eq!(order.status, OrderStatus::Open);
        exchange.step(1);
        assert_eq!(exchange.orders()[0].status, OrderStatus::Filled);
        assert_eq!(exchange.fills()[0].liquidity, Liquidity::Maker);
        assert_eq!(exchange.fills()[0].price, 100.0);
    }

    #[test]
    fn leverage_cap_rejects_large_order() {
        let mut exchange = PaperExchange::new(
            ExchangeConfig {
                max_leverage: 1.0,
                ..ExchangeConfig::default()
            },
            frames(),
        )
        .unwrap();
        let order = exchange
            .place_order(NewOrder {
                side: Side::Buy,
                kind: OrderKind::Market,
                qty: 200.0,
                limit_price: None,
                tif: TimeInForce::Ioc,
                reduce_only: false,
                client_order_id: None,
            })
            .unwrap();
        assert_eq!(order.status, OrderStatus::Rejected);
    }
}
