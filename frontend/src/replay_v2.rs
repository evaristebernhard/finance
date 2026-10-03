//! Read-only, offset-backed replay queries. No artifact files are created or changed.
use serde::de::IgnoredAny;
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap};
use std::fs::File;
use std::io::{BufRead, BufReader, Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

#[path = "../../systems/quant_replay_engine/crates/exchange_sim/src/valuation.rs"]
mod valuation;

#[derive(Debug)]
struct Event {
    id: String,
    kind: String,
    timestamp: u64,
    clock: u64,
    offset: u64,
    len: u64,
    links: BTreeMap<String, String>,
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum Scalar {
    Text(String),
    Integer(u64),
}
impl Scalar {
    fn string(&self) -> String {
        match self {
            Self::Text(s) => s.clone(),
            Self::Integer(n) => n.to_string(),
        }
    }
}
#[derive(Default)]
struct EventHeader {
    event_id: Option<String>,
    event_type: String,
    replay_ts: String,
}
fn skip_ws(bytes: &[u8], mut p: usize) -> usize {
    while p < bytes.len() && bytes[p].is_ascii_whitespace() {
        p += 1;
    }
    p
}
fn string_end(bytes: &[u8], start: usize) -> Result<usize, String> {
    if bytes.get(start) != Some(&b'"') {
        return Err("expected JSON string".into());
    }
    let mut p = start + 1;
    let mut escaped = false;
    while p < bytes.len() {
        let c = bytes[p];
        p += 1;
        if escaped {
            escaped = false;
            continue;
        }
        if c == b'\\' {
            escaped = true;
        } else if c == b'"' {
            return Ok(p);
        }
    }
    Err("unterminated JSON string".into())
}
fn skip_value(bytes: &[u8], start: usize) -> Result<usize, String> {
    if bytes.get(start) == Some(&b'"') {
        return string_end(bytes, start);
    }
    if matches!(bytes.get(start), Some(b'{' | b'[')) {
        let mut p = start;
        let mut depth = 0i32;
        let mut quoted = false;
        let mut escaped = false;
        while p < bytes.len() {
            let c = bytes[p];
            p += 1;
            if quoted {
                if escaped {
                    escaped = false;
                } else if c == b'\\' {
                    escaped = true;
                } else if c == b'"' {
                    quoted = false;
                }
                continue;
            }
            match c {
                b'"' => quoted = true,
                b'{' | b'[' => depth += 1,
                b'}' | b']' => {
                    depth -= 1;
                    if depth == 0 {
                        return Ok(p);
                    }
                }
                _ => (),
            }
        }
        return Err("unterminated JSON object".into());
    }
    let mut p = start;
    while p < bytes.len() && !matches!(bytes[p], b',' | b'}' | b']') {
        p += 1;
    }
    Ok(p)
}
fn scalar_text(bytes: &[u8]) -> Result<String, String> {
    if bytes.first() == Some(&b'"') {
        serde_json::from_slice::<String>(bytes).map_err(|e| e.to_string())
    } else {
        std::str::from_utf8(bytes)
            .map(str::to_owned)
            .map_err(|e| e.to_string())
    }
}
fn scan_header(line: &str) -> Result<EventHeader, String> {
    let b = line.as_bytes();
    let mut p = skip_ws(b, 0);
    if b.get(p) != Some(&b'{') {
        return Err("event must be a JSON object".into());
    }
    p += 1;
    let mut h = EventHeader::default();
    loop {
        p = skip_ws(b, p);
        if b.get(p) == Some(&b'}') {
            break;
        }
        let ks = p;
        let ke = string_end(b, p)?;
        let key = &b[ks..ke];
        p = skip_ws(b, ke);
        if b.get(p) != Some(&b':') {
            return Err("expected colon in event header".into());
        }
        p = skip_ws(b, p + 1);
        if key == b"\"payload\""
            && h.event_id.is_some()
            && !h.event_type.is_empty()
            && !h.replay_ts.is_empty()
        {
            break;
        }
        let end = skip_value(b, p)?;
        let raw = &b[p..end];
        match key {
            b"\"event_id\"" => h.event_id = Some(scalar_text(raw)?),
            b"\"event_type\"" => h.event_type = scalar_text(raw)?,
            b"\"replay_ts\"" => h.replay_ts = scalar_text(raw)?,
            _ => (),
        }
        p = skip_ws(b, end);
        match b.get(p) {
            Some(b',') => p += 1,
            Some(b'}') => break,
            _ => return Err("expected comma in event header".into()),
        }
    }
    if h.event_type.is_empty() || h.replay_ts.is_empty() {
        return Err("missing event_type or replay_ts".into());
    }
    Ok(h)
}
#[derive(Deserialize)]
struct L2Event {
    payload: L2Payload,
}
#[derive(Deserialize)]
struct L2Payload {
    #[serde(default)]
    update_count: Option<usize>,
    #[serde(default)]
    snapshot_update_count: Option<usize>,
    #[serde(default)]
    incremental_update_count: Option<usize>,
    #[serde(default)]
    book: Option<IgnoredAny>,
}
#[derive(Deserialize)]
struct ReplayIndex {
    event_count: usize,
    events: Vec<ReplayIndexEvent>,
}
#[derive(Deserialize)]
struct ReplayIndexEvent {
    event_id: Scalar,
    byte_offset: u64,
    byte_len: u64,
}

#[derive(Debug)]
pub struct Repository {
    path: PathBuf,
    pub manifest: Value,
    events: Vec<Event>,
    ids: HashMap<String, usize>,
    kinds: HashMap<String, Vec<usize>>,
    links: HashMap<(String, String), Vec<usize>>,
    quotes: Vec<(usize, Value)>,
    accounts: Vec<(usize, Value)>,
    books: Vec<(usize, usize, usize)>,
    pnl: Vec<(usize, Value)>,
    initial: Value,
    pub timestamp_regressions: usize,
}

fn scalar(v: &Value) -> Option<String> {
    v.as_str()
        .map(str::to_owned)
        .or_else(|| v.as_u64().map(|n| n.to_string()))
}
fn n(v: &Value, k: &str) -> Option<f64> {
    v.get(k).and_then(Value::as_f64)
}
fn payload(event: &Value) -> &Value {
    let p = event.get("payload").unwrap_or(&Value::Null);
    p.get("payload").unwrap_or(p)
}
fn find(v: &Value, key: &str) -> Option<String> {
    v.get(key).and_then(scalar).or_else(|| match v {
        Value::Object(o) => o.values().find_map(|v| find(v, key)),
        _ => None,
    })
}
fn wire(mut v: Value) -> Value {
    match &mut v {
        Value::Object(o) => {
            for (k, value) in o {
                if k.ends_with("ts_us")
                    || k == "replay_ts"
                    || k == "ts"
                    || k.ends_with("_id")
                    || k == "event_id"
                {
                    if let Some(s) = scalar(value) {
                        *value = Value::String(s);
                    }
                } else {
                    *value = wire(value.take());
                }
            }
        }
        Value::Array(a) => {
            for v in a {
                *v = wire(v.take());
            }
        }
        _ => (),
    }
    v
}
fn quote(v: &Value) -> Value {
    let mid = n(v, "mid").or_else(|| Some((n(v, "bid")? + n(v, "ask")?) / 2.0));
    json!({"bid": n(v,"bid"), "ask": n(v,"ask"), "mid": mid,
    "bidQty": n(v,"bid_qty"), "askQty": n(v,"ask_qty"),
    "spreadBps": mid.and_then(|m| Some((n(v,"ask")? - n(v,"bid")?) / m * 10000.0)),
    "microprice": match (n(v,"bid"),n(v,"ask"),n(v,"bid_qty"),n(v,"ask_qty")) {
        (Some(b),Some(a),Some(bq),Some(aq)) if bq+aq > 0.0 => Some((a*bq+b*aq)/(bq+aq)), _ => mid
    }})
}
fn at<T>(values: &[(usize, T)], end: usize) -> Option<&T> {
    values
        .get(values.partition_point(|(p, _)| *p <= end).checked_sub(1)?)
        .map(|(_, v)| v)
}
fn account_mark(account: &Value, q: Option<&Value>) -> Value {
    if !account.is_object() {
        return Value::Null;
    }
    let mut a = account.clone();
    if let (Some(c), Some(p), Some(avg), Some(mid)) = (
        n(&a, "cash"),
        n(&a, "position_qty"),
        n(&a, "avg_entry_price"),
        q.and_then(|q| n(q, "mid")),
    ) {
        let (u, e, no, l) = valuation::mark_account(c, p, avg, mid);
        a["unrealized_pnl"] = json!(u);
        a["equity"] = json!(e);
        a["notional"] = json!(no);
        a["leverage"] = json!(l);
    } else if n(&a, "position_qty") != Some(0.0) {
        for k in ["unrealized_pnl", "equity", "notional", "leverage"] {
            a[k] = Value::Null;
        }
    }
    a
}

impl Repository {
    pub fn open(dir: &Path) -> Result<Self, String> {
        let manifest: Value = serde_json::from_reader(
            File::open(dir.join("manifest.json")).map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.to_string())?;
        let initial = manifest.get("exchange_config").and_then(|v|n(v,"starting_cash")).or_else(|| n(&manifest,"starting_cash"))
            .map(|cash|json!({"initial_cash":cash,"cash":cash,"position_qty":0.0,"avg_entry_price":0.0,"realized_pnl":0.0,"unrealized_pnl":0.0,"fees_paid":0.0,"equity":cash,"notional":0.0,"leverage":0.0})).unwrap_or(Value::Null);
        let mut r = Self {
            path: dir.join("events.ndjson"),
            manifest,
            events: vec![],
            ids: HashMap::new(),
            kinds: HashMap::new(),
            links: HashMap::new(),
            quotes: vec![],
            accounts: vec![],
            books: vec![],
            pnl: vec![],
            initial,
            timestamp_regressions: 0,
        };
        // Validate existing offsets as we stream; old runs build the same index in memory.
        let existing: Option<ReplayIndex> = if dir.join("replay_index.json").exists() {
            Some(
                serde_json::from_reader(
                    File::open(dir.join("replay_index.json")).map_err(|e| e.to_string())?,
                )
                .map_err(|e| format!("invalid replay index: {e}"))?,
            )
        } else {
            None
        };
        let mut reader = BufReader::new(File::open(&r.path).map_err(|e| e.to_string())?);
        let mut line = String::new();
        let mut offset = 0;
        let mut clock = 0;
        let mut updates = 0;
        let mut snapshots = 0;
        while reader.read_line(&mut line).map_err(|e| e.to_string())? > 0 {
            let len = line.len() as u64;
            if !line.trim().is_empty() {
                let header = scan_header(&line)
                    .map_err(|e| format!("invalid event header at byte {offset}: {e}"))?;
                let pos = r.events.len();
                let id = header
                    .event_id
                    .map(|value| value)
                    .unwrap_or_else(|| (pos + 1).to_string());
                let kind = header.event_type;
                let timestamp = header
                    .replay_ts
                    .parse::<u64>()
                    .map_err(|_| format!("invalid replay_ts at event {pos}"))?;
                if timestamp < clock {
                    r.timestamp_regressions += 1;
                }
                clock = clock.max(timestamp);
                if let Some(index) = &existing {
                    let e = index
                        .events
                        .get(pos)
                        .ok_or("replay index has fewer events than events.ndjson")?;
                    if e.byte_offset != offset || e.byte_len != len || e.event_id.string() != id {
                        return Err(format!("replay index mismatch at event {pos}"));
                    }
                }
                r.kinds.entry(kind.clone()).or_default().push(pos);
                r.events.push(Event {
                    id: id.clone(),
                    kind: kind.clone(),
                    timestamp,
                    clock,
                    offset,
                    len,
                    links: BTreeMap::new(),
                });
                if kind == "market_l2_batch" {
                    // Skip potentially large update/book arrays while extracting the three counters.
                    let l2: L2Event = serde_json::from_str(&line)
                        .map_err(|e| format!("invalid L2 payload at event {pos}: {e}"))?;
                    if l2.payload.book.is_some() {
                        updates += l2.payload.update_count.unwrap_or(0);
                        snapshots += usize::from(
                            l2.payload.snapshot_update_count.unwrap_or(0) > 0
                                && l2.payload.incremental_update_count.unwrap_or(0) == 0,
                        );
                        r.books.push((pos, updates, snapshots));
                    }
                } else if matches!(
                    kind.as_str(),
                    "market_quote"
                        | "strategy_signal"
                        | "order_intent"
                        | "order_arrival"
                        | "fill_created"
                        | "fill"
                        | "position_snapshot"
                        | "portfolio_state_on_change"
                ) {
                    let raw: Value = serde_json::from_str(&line)
                        .map_err(|e| format!("invalid payload at event {pos}: {e}"))?;
                    let p = payload(&raw);
                    let link_keys: &[&str] = match kind.as_str() {
                        "strategy_signal" => &["observed_ts_us", "signal_id"],
                        "order_intent" => &["intent_id", "client_order_id", "observed_ts_us"],
                        "order_arrival" => &["intent_id", "client_order_id", "order_id"],
                        "fill_created" | "fill" => {
                            &["intent_id", "order_id", "fill_id", "client_order_id"]
                        }
                        "position_snapshot" | "portfolio_state_on_change" | "portfolio_state" => {
                            &["fill_id", "intent_id", "order_id"]
                        }
                        _ => &[],
                    };
                    let mut links = BTreeMap::new();
                    for key in link_keys {
                        if let Some(value) = find(p, key) {
                            r.links
                                .entry(((*key).into(), value.clone()))
                                .or_default()
                                .push(pos);
                            links.insert((*key).into(), value);
                        }
                    }
                    r.events[pos].links = links;
                    if kind == "market_quote" {
                        r.quotes.push((pos, quote(p.get("frame").unwrap_or(p))));
                    }
                    if let Some(a) = p.get("account").filter(|a| a.is_object()) {
                        r.accounts.push((pos, a.clone()));
                    }
                    if kind == "market_quote" || p.get("account").is_some() || pos == 0 {
                        let a = r.account(pos);
                        r.pnl.push((pos,json!({"eventPos":pos,"timestamp":timestamp.to_string(),"realizedPnl":n(&a,"realized_pnl"),"unrealizedPnl":n(&a,"unrealized_pnl"),"netPnl":n(&a,"equity").and_then(|e|Some(e-n(&a,"initial_cash")?))})));
                    }
                }
                if r.ids.insert(id.clone(), pos).is_some() {
                    return Err(format!("duplicate event id {id}"));
                }
            }
            offset += len;
            line.clear();
        }
        if r.events.is_empty() {
            return Err("run has no events".into());
        }
        if existing
            .as_ref()
            .is_some_and(|v| v.event_count != r.len() || v.events.len() != r.len())
        {
            return Err("replay index event_count mismatch".into());
        }
        Ok(r)
    }
    pub fn len(&self) -> usize {
        self.events.len()
    }
    fn raw(&self, pos: usize) -> Result<Value, String> {
        let e = self.events.get(pos).ok_or("event position out of range")?;
        let mut file = File::open(&self.path).map_err(|e| e.to_string())?;
        file.seek(SeekFrom::Start(e.offset))
            .map_err(|e| e.to_string())?;
        let mut bytes = vec![0; e.len as usize];
        file.read_exact(&mut bytes).map_err(|e| e.to_string())?;
        serde_json::from_slice(&bytes).map_err(|e| e.to_string())
    }
    fn stage(&self, pos: Option<usize>) -> Result<Value, String> {
        pos.map(|pos|self.raw(pos).map(|e|json!({"eventId":self.events[pos].id,"eventPos":pos,"timestamp":self.events[pos].timestamp.to_string(),"data":wire(payload(&e).clone())}))).unwrap_or(Ok(Value::Null))
    }
    fn account(&self, end: usize) -> Value {
        account_mark(
            at(&self.accounts, end).unwrap_or(&self.initial),
            at(&self.quotes, end),
        )
    }
    fn latest(&self, kind: &str, end: usize) -> Option<usize> {
        let ps = self.kinds.get(kind)?;
        ps.get(ps.partition_point(|p| *p <= end).checked_sub(1)?)
            .copied()
    }
    fn related(
        &self,
        source: usize,
        kind: &str,
        end: usize,
        keys: &[&str],
        unique: bool,
    ) -> Option<usize> {
        for key in keys {
            if let Some(id) = self.events[source].links.get(*key) {
                let ps = self.links.get(&(key.to_string(), id.clone()))?;
                let matches: Vec<_> = ps
                    .iter()
                    .copied()
                    .filter(|p| *p <= end && self.events[*p].kind == kind)
                    .collect();
                if !matches.is_empty() && (!unique || matches.len() == 1) {
                    return matches.last().copied();
                }
            }
        }
        None
    }
    fn chain(&self, source: usize, end: usize) -> Result<Value, String> {
        let kind = &self.events[source].kind;
        let intent = if kind == "order_intent" {
            Some(source)
        } else {
            self.related(
                source,
                "order_intent",
                end,
                &["intent_id", "client_order_id"],
                true,
            )
        };
        let arrival = if kind == "order_arrival" {
            Some(source)
        } else {
            self.related(
                source,
                "order_arrival",
                end,
                &["intent_id", "order_id", "client_order_id"],
                true,
            )
        };
        let fill = if kind == "fill_created" || kind == "fill" {
            Some(source)
        } else {
            self.related(
                source,
                "fill_created",
                end,
                &["intent_id", "order_id"],
                true,
            )
            .or_else(|| self.related(source, "fill", end, &["intent_id", "order_id"], true))
        };
        let signal = if kind == "strategy_signal" {
            Some(source)
        } else {
            intent.and_then(|p| {
                self.related(
                    p,
                    "strategy_signal",
                    p,
                    &["signal_id", "observed_ts_us"],
                    true,
                )
            })
        };
        let account = fill.and_then(|p| {
            self.related(p, "position_snapshot", end, &["fill_id"], true)
                .or_else(|| {
                    self.related(
                        p,
                        "portfolio_state_on_change",
                        end,
                        &["fill_id", "intent_id", "order_id"],
                        true,
                    )
                })
        });
        let stages = [
            ("signal", signal),
            ("intent", intent),
            ("arrival", arrival),
            ("fill", fill),
            ("account", account),
        ];
        let mut result = serde_json::Map::new();
        let mut missing = vec![];
        for (name, pos) in stages {
            if pos.is_none() {
                missing.push(name);
            }
            result.insert(name.into(), self.stage(pos)?);
        }
        result.insert("missing".into(), json!(missing));
        Ok(Value::Object(result))
    }
    pub fn inspect(&self, id: &str, end: usize) -> Result<Value, String> {
        let pos = *self.ids.get(id).ok_or("unknown event id")?;
        if pos > end {
            return Err("event is beyond replay cursor".into());
        }
        Ok(json!({"rawEvent":wire(self.raw(pos)?),"chain":self.chain(pos,end)?}))
    }
    pub fn rows(
        &self,
        kind: Option<&str>,
        offset: usize,
        limit: usize,
        end: usize,
    ) -> Result<Value, String> {
        let end = end.min(self.len() - 1);
        let typed = kind.and_then(|kind| self.kinds.get(kind));
        let total = typed
            .map(|ps| ps.partition_point(|p| *p <= end))
            .unwrap_or(end + 1);
        let page_limit = limit.clamp(1, 200);
        let mut rows = vec![];
        for page_index in offset..offset.saturating_add(page_limit).min(total) {
            let pos = typed
                .map(|ps| ps[total - 1 - page_index])
                .unwrap_or(end - page_index);
            let raw = self.raw(pos)?;
            let p = payload(&raw);
            let order = p
                .get("intent")
                .and_then(|i| i.get("order"))
                .or_else(|| p.get("order"));
            let fill = p.get("fill");
            let arrival = self
                .related(pos, "order_arrival", end, &["intent_id", "order_id", "client_order_id"], true)
                .map(|arrival_pos| self.raw(arrival_pos))
                .transpose()?;
            let arrival_payload = arrival.as_ref().map(payload);
            let intent_event = if self.events[pos].kind == "order_intent" {
                Some(raw.clone())
            } else {
                self.related(pos, "order_intent", end, &["intent_id", "client_order_id"], true)
                    .map(|intent_pos| self.raw(intent_pos))
                    .transpose()?
            };
            let intent_payload = intent_event.as_ref().map(payload);
            rows.push(json!({"eventId":self.events[pos].id,"eventPos":pos,"timestamp":self.events[pos].timestamp.to_string(),"eventType":self.events[pos].kind,"source":raw["source"],
                "intentId":find(p,"intent_id"),"orderId":find(p,"order_id"),"fillId":find(p,"fill_id").or_else(||fill.and_then(|f|scalar(&f["id"]))),
                "side":fill.or(order).and_then(|v|v.get("side")),"qty":fill.or(order).and_then(|v|n(v,"qty")),"price":fill.and_then(|v|n(v,"price")),"fee":n(p,"fee").or_else(||fill.and_then(|f|n(f,"fee"))),
                "signal":n(p,"signal").or_else(||arrival_payload.and_then(|v|n(v,"signal"))).or_else(||intent_payload.and_then(|v|n(v,"signal"))),
                "threshold":n(p,"threshold").or_else(||intent_payload.and_then(|v|n(v,"threshold"))),
                "reason":find(p,"reason").or_else(||arrival_payload.and_then(|v|find(v,"reason"))).or_else(||intent_payload.and_then(|v|find(v,"reason"))),
                "actualLatencyUs":n(p,"actual_latency_us").or_else(||arrival_payload.and_then(|v|n(v,"actual_latency_us"))),
                "latencySlippageBps":n(p,"latency_slippage_bps").or_else(||arrival_payload.and_then(|v|n(v,"latency_slippage_bps"))),
                "realizedPnlDelta":n(p,"realized_pnl_delta"),
                "netPnlDelta":n(p,"net_pnl_delta").or_else(||p.get("attribution").and_then(|a|n(a,"net_pnl"))),
                "grossExecutionPnl":p.get("attribution").and_then(|a|n(a,"gross_execution_pnl")),
                "spreadExecutionCost":p.get("attribution").and_then(|a|n(a,"spread_execution_cost")),
                "status":if self.events[pos].kind=="order_intent" {arrival_payload.map(|e|e["order"]["status"].clone()).unwrap_or(json!("waiting"))} else {Value::Null}}));
        }
        Ok(json!({"rows":rows,"total":total,"offset":offset,"limit":page_limit,"cursorUpper":end}))
    }
    pub fn window(&self, start: Option<u64>, stop: Option<u64>, max: usize, end: usize) -> Value {
        let end = end.min(self.len() - 1);
        let start = start.unwrap_or(0);
        let stop = stop.unwrap_or(u64::MAX);
        let upper_clock = stop.min(self.events[end].clock);
        let begin_pos = self
            .events
            .partition_point(|event| event.clock < start)
            .min(end + 1);
        let stop_pos = self
            .events
            .partition_point(|event| event.clock <= upper_clock)
            .min(end + 1);
        let q_start = self.quotes.partition_point(|(pos, _)| *pos < begin_pos);
        let q_stop = self.quotes.partition_point(|(pos, _)| *pos < stop_pos);
        let q: Vec<_> = self.quotes[q_start..q_stop].iter().collect();
        let p_start = self.pnl.partition_point(|(pos, _)| *pos < begin_pos);
        let p_stop = self.pnl.partition_point(|(pos, _)| *pos < stop_pos);
        let p: Vec<_> = self.pnl[p_start..p_stop].iter().collect();
        let prices = sample(&q, max, |p| n(&p.1, "mid").unwrap_or(0.0))
            .into_iter()
            .map(|(pos, v)| {
                let mut v = v.clone();
                v["eventPos"] = json!(pos);
                v["timestamp"] = json!(self.events[*pos].timestamp.to_string());
                v["clockTimestamp"] = json!(self.events[*pos].clock.to_string());
                v
            })
            .collect::<Vec<_>>();
        let pnl = sample(&p, max, |p| n(&p.1, "netPnl").unwrap_or(0.0))
            .into_iter()
            .map(|(pos, v)| {
                let mut point = v.clone();
                point["clockTimestamp"] = json!(self.events[*pos].clock.to_string());
                point
            })
            .collect::<Vec<_>>();
        let mut markers = vec![];
        for kind in [
            "strategy_signal",
            "order_intent",
            "order_arrival",
            "fill_created",
            "fill",
        ] {
            if let Some(ps) = self.kinds.get(kind) {
                let first = ps.partition_point(|p| self.events[*p].clock < start);
                let last = ps
                    .partition_point(|p| self.events[*p].clock <= upper_clock)
                    .min(end + 1);
                for pos in ps[first..last].iter().copied() {
                    let raw = self.raw(pos).ok();
                    let marker_payload = raw.as_ref().map(payload);
                    let marker_fill = marker_payload.and_then(|p| p.get("fill"));
                    let marker_order = marker_payload
                        .and_then(|p| p.get("intent").and_then(|i| i.get("order")).or_else(|| p.get("order")));
                    markers.push(json!({
                        "eventId":self.events[pos].id,
                        "eventPos":pos,
                        "timestamp":self.events[pos].timestamp.to_string(),
                        "clockTimestamp":self.events[pos].clock.to_string(),
                        "eventType":kind,
                        "mid":at(&self.quotes,pos).and_then(|q|n(q,"mid")),
                        "price":marker_fill.and_then(|f|n(f,"price")),
                        "side":marker_fill.or(marker_order).and_then(|v|v.get("side")).and_then(Value::as_str),
                        "signal":marker_payload.and_then(|p|n(p,"signal"))
                    }));
                }
            }
        }
        // Marker lists can also be large; preserve bounded transport and disclose count.
        markers.sort_by_key(|v| v["eventPos"].as_u64().unwrap_or(0));
        let marker_count = markers.len();
        if markers.len() > max.clamp(2, 10000) {
            let refs: Vec<_> = markers.iter().collect();
            markers = sample(&refs, max, |m| m["eventPos"].as_f64().unwrap_or(0.0))
                .into_iter()
                .cloned()
                .collect();
        }
        json!({"prices":prices,"pnl":pnl,"markers":markers,"markerCount":marker_count,"cursorUpper":end})
    }
    pub fn snapshot(
        &self,
        cursor: usize,
        selected: Option<&str>,
        playing: bool,
        speed: f64,
    ) -> Result<Value, String> {
        let end = cursor.min(self.len() - 1);
        let event = &self.events[end];
        let selected = selected
            .and_then(|id| self.ids.get(id).copied())
            .filter(|p| {
                *p <= end && matches!(self.events[*p].kind.as_str(), "fill" | "fill_created")
            });
        let focus = selected.unwrap_or_else(|| {
            if matches!(
                event.kind.as_str(),
                "order_intent" | "order_arrival" | "fill_created" | "fill" | "strategy_signal"
            ) {
                end
            } else {
                self.latest("fill_created", end)
                    .or_else(|| self.latest("order_intent", end))
                    .unwrap_or(end)
            }
        });
        let book_pos = self
            .books
            .partition_point(|(p, _, _)| *p <= end)
            .checked_sub(1);
        let book = book_pos.map(|i| self.raw(self.books[i].0)).transpose()?;
        let q = at(&self.quotes, end).cloned().unwrap_or(Value::Null);
        let fallback = |price: &str, qty: &str| {
            if q[price].is_number() {
                json!([{"price":q[price],"qty":q[qty],"cumulative_qty":q[qty]}])
            } else {
                json!([])
            }
        };
        let quality = self
            .manifest
            .get("l2_preflight")
            .cloned()
            .unwrap_or(json!({"status":"top_of_book","warnings":[]}));
        Ok(
            json!({"schemaVersion":2,"runId":self.manifest["run_id"],"symbol":self.manifest["exchange_config"]["symbol"],"datasetDate":self.manifest.get("canonical_date").or_else(||self.manifest.get("dataset_date")).and_then(Value::as_str).or_else(||self.manifest.get("source_label").and_then(Value::as_str).and_then(|s|s.rsplit(':').next())),"strategy":self.manifest.get("profile").or_else(||self.manifest.get("strategy_profile")),"executionModel":self.manifest["fill_model"],"delayUs":self.manifest["latency_us"],"feeBps":self.manifest["exchange_config"]["fee_bps"],
            "cursor":end,"eventCount":self.len(),"eventId":event.id,"eventType":event.kind,"timestamp":event.timestamp.to_string(),"clockTimestamp":event.clock.to_string(),"startTimestamp":self.events[0].clock.to_string(),"endTimestamp":self.events.last().unwrap().clock.to_string(),"timestampRegressions":self.timestamp_regressions,"playing":playing,"speed":speed,
            "quote":q,"account":self.account(end),"chain":self.chain(focus,end)?,"selectedFillEventId":selected.map(|p|self.events[p].id.clone()),
            "orderBook":{"bids":book.as_ref().map(|b|payload(b)["book"]["bid_depth"].clone()).unwrap_or_else(||fallback("bid","bidQty")),"asks":book.as_ref().map(|b|payload(b)["book"]["ask_depth"].clone()).unwrap_or_else(||fallback("ask","askQty")),"updateCount":book_pos.map(|i|self.books[i].1).unwrap_or(0),"snapshotBatchCount":book_pos.map(|i|self.books[i].2).unwrap_or(0),"quality":quality}}),
        )
    }
}

// First/last and each bucket's extrema, preserving event order and the point cap.
fn sample<'a, T, F>(values: &[&'a T], max: usize, value: F) -> Vec<&'a T>
where
    F: Fn(&T) -> f64,
{
    let max = max.clamp(2, 10000);
    if values.len() <= max {
        return values.to_vec();
    }
    if max < 4 {
        return vec![values[0], values[values.len() - 1]];
    }
    let buckets = (max - 2) / 2;
    let interior = values.len() - 2;
    let mut indices = vec![0, values.len() - 1];
    for b in 0..buckets {
        let start = 1 + b * interior / buckets;
        let end = 1 + (b + 1) * interior / buckets;
        let range = start..end;
        if let Some(min) = range
            .clone()
            .min_by(|a, b| value(values[*a]).total_cmp(&value(values[*b])))
        {
            indices.push(min);
        }
        if let Some(max) = range.max_by(|a, b| value(values[*a]).total_cmp(&value(values[*b]))) {
            indices.push(max);
        }
    }
    indices.sort_unstable();
    indices.dedup();
    indices.into_iter().map(|i| values[i]).collect()
}

pub struct Session {
    pub repository: Repository,
    pub id: u64,
    pub version: u64,
    pub cursor: usize,
    pub playing: bool,
    pub speed: f64,
    pub selected: Option<String>,
    last_tick: Instant,
    virtual_clock: f64,
}
impl Session {
    pub fn new(repository: Repository, id: u64) -> Self {
        let clock = repository.events[0].clock as f64;
        Self {
            repository,
            id,
            version: 0,
            cursor: 0,
            playing: false,
            speed: 1.0,
            selected: None,
            last_tick: Instant::now(),
            virtual_clock: clock,
        }
    }
    pub fn reanchor(&mut self) {
        self.virtual_clock = self.repository.events[self.cursor].clock as f64;
        self.last_tick = Instant::now();
    }
    pub fn advance(&mut self, elapsed: Duration) {
        if !self.playing {
            return;
        }
        self.virtual_clock += elapsed.as_secs_f64() * 1_000_000.0 * self.speed;
        let end = self
            .repository
            .events
            .partition_point(|e| e.clock as f64 <= self.virtual_clock)
            .saturating_sub(1);
        self.cursor = self.cursor.max(end);
        if self.cursor + 1 >= self.repository.len() {
            self.playing = false;
        }
    }
    pub fn tick(&mut self) {
        let now = Instant::now();
        let elapsed = now.duration_since(self.last_tick);
        self.last_tick = now;
        self.advance(elapsed);
    }
    pub fn command(&mut self, command: &str) -> Result<(), String> {
        if self.playing {
            self.tick();
        }
        match command {
            "play" => self.playing = self.cursor + 1 < self.repository.len(),
            "pause" => self.playing = false,
            "stepBack" => {
                self.playing = false;
                self.cursor = self.cursor.saturating_sub(1);
            }
            "stepForward" => {
                self.playing = false;
                self.cursor = (self.cursor + 1).min(self.repository.len() - 1);
            }
            "reset" => {
                self.playing = false;
                self.cursor = 0;
                self.selected = None;
            }
            "speedUp" => self.speed = (self.speed * 2.0).min(16.0),
            "speedDown" => self.speed = (self.speed / 2.0).max(0.25),
            _ => return Err(format!("unknown command {command}")),
        }
        self.last_tick = Instant::now();
        if matches!(command, "stepBack" | "stepForward" | "reset") {
            self.virtual_clock = self.repository.events[self.cursor].clock as f64;
        }
        Ok(())
    }
    pub fn seek(&mut self, fraction: f64) -> Result<(), String> {
        if !fraction.is_finite() {
            return Err("seek must be finite".into());
        }
        self.playing = false;
        self.cursor =
            (fraction.clamp(0.0, 1.0) * (self.repository.len() - 1) as f64).round() as usize;
        self.selected = None;
        self.reanchor();
        Ok(())
    }
    pub fn snapshot(&mut self) -> Result<Value, String> {
        self.version += 1;
        let mut v = self.repository.snapshot(
            self.cursor,
            self.selected.as_deref(),
            self.playing,
            self.speed,
        )?;
        v["sessionId"] = json!(self.id.to_string());
        v["version"] = json!(self.version);
        Ok(v)
    }
    pub fn envelope(&self, mut value: Value) -> Value {
        value["sessionId"] = json!(self.id.to_string());
        value["version"] = json!(self.version);
        value
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture(initial: bool) -> (PathBuf, Repository) {
        let dir = std::env::temp_dir().join(format!(
            "qrs-v2-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let manifest = if initial {
            json!({"run_id":"test","exchange_config":{"starting_cash":1000.0,"symbol":"CCUSDT"}})
        } else {
            json!({"run_id":"test"})
        };
        std::fs::write(dir.join("manifest.json"), manifest.to_string()).unwrap();
        std::fs::write(
            dir.join("summary.json"),
            json!({"final_account":{"equity":999999.0}}).to_string(),
        )
        .unwrap();
        let events = vec![
            ("run_start", 0, json!({})),
            (
                "market_quote",
                1_000_000,
                json!({"frame":{"bid":9.0,"ask":11.0,"mid":10.0,"bid_qty":2.0,"ask_qty":1.0}}),
            ),
            (
                "strategy_signal",
                1_000_000,
                json!({"observed_ts_us":1000000,"signal":0.8}),
            ),
            (
                "order_intent",
                1_000_000,
                json!({"intent_id":1,"observed_ts_us":1000000,"intent":{"order":{"side":"buy","qty":2.0}}}),
            ),
            (
                "order_arrival",
                2_000_000,
                json!({"intent_id":1,"order_id":7,"order":{"status":"filled"},"arrival_ts_us":2000000}),
            ),
            (
                "fill_created",
                2_000_000,
                json!({"intent_id":1,"order_id":7,"fill_id":8,"fill":{"id":8,"order_id":7,"price":11.0,"qty":2.0,"fee":1.0}}),
            ),
            (
                "position_snapshot",
                2_000_000,
                json!({"fill_id":8,"account":{"initial_cash":1000.0,"cash":977.0,"position_qty":2.0,"avg_entry_price":11.0,"realized_pnl":0.0,"fees_paid":1.0}}),
            ),
            (
                "market_quote",
                3_000_000,
                json!({"frame":{"bid":14.0,"ask":16.0,"mid":15.0}}),
            ),
            (
                "strategy_signal",
                3_000_000,
                json!({"observed_ts_us":3000000,"signal":-0.7}),
            ),
            ("run_end", 4_000_000, json!({})),
        ];
        let lines = events
            .into_iter()
            .enumerate()
            .map(|(i, (kind, t, p))| {
                json!({"event_id":i+1,"event_type":kind,"replay_ts":t.to_string(),"payload":p})
                    .to_string()
            })
            .collect::<Vec<_>>()
            .join("\n");
        std::fs::write(dir.join("events.ndjson"), lines).unwrap();
        let r = Repository::open(&dir).unwrap();
        (dir, r)
    }
    #[test]
    fn cursor_visibility_and_explicit_causality() {
        let (dir, r) = fixture(true);
        assert!(r.snapshot(0, None, false, 1.0).unwrap()["quote"].is_null());
        let intent = r.snapshot(3, None, false, 1.0).unwrap();
        assert_eq!(intent["account"]["equity"], 1000.0);
        assert!(intent["chain"]["arrival"].is_null());
        assert!(intent["chain"]["fill"].is_null());
        assert_eq!(
            r.rows(Some("order_intent"), 0, 20, 3).unwrap()["rows"][0]["status"],
            "waiting"
        );
        assert!(r.inspect("6", 3).is_err());
        let old = r.snapshot(8, Some("6"), false, 1.0).unwrap();
        assert_eq!(old["chain"]["signal"]["eventId"], "3");
        assert_eq!(old["chain"]["account"]["eventId"], "7");
        assert_eq!(old["account"]["equity"], 1007.0);
        assert_eq!(old["account"]["unrealized_pnl"], 8.0);
        assert_eq!(
            r.window(None, None, 10, 8)["pnl"]
                .as_array()
                .unwrap()
                .last()
                .unwrap()["netPnl"],
            7.0
        );
        assert_eq!(
            r.inspect("6", 8).unwrap()["rawEvent"]["payload"]["intent_id"],
            "1"
        );
        std::fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn absent_initial_account_is_unavailable() {
        let (dir, r) = fixture(false);
        assert!(r.snapshot(3, None, false, 1.0).unwrap()["account"].is_null());
        std::fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn wall_clock_speed_pause_seek_and_equal_timestamp_order() {
        let (dir, r) = fixture(true);
        let mut s = Session::new(r, 1);
        s.command("play").unwrap();
        s.advance(Duration::from_millis(250));
        assert_eq!(s.cursor, 0);
        s.advance(Duration::from_millis(750));
        assert_eq!(s.cursor, 3);
        s.command("stepForward").unwrap();
        assert_eq!(s.cursor, 4);
        assert!(!s.playing);
        s.seek(0.0).unwrap();
        s.speed = 0.25;
        s.command("play").unwrap();
        s.advance(Duration::from_secs(4));
        assert_eq!(s.cursor, 3);
        s.command("pause").unwrap();
        let cursor = s.cursor;
        s.advance(Duration::from_secs(9));
        assert_eq!(s.cursor, cursor);
        s.seek(0.0).unwrap();
        s.speed = 16.0;
        s.command("play").unwrap();
        s.advance(Duration::from_secs(1));
        assert_eq!(s.cursor, 9);
        assert!(!s.playing);
        assert!(s.seek(f64::NAN).is_err());
        assert_eq!(s.snapshot().unwrap()["sessionId"], "1");
        std::fs::remove_dir_all(dir).unwrap();
    }
    #[test]
    fn downsampling_retains_extrema_and_cap() {
        let mut values = vec![0.0; 1000];
        values[212] = -100.0;
        values[645] = 100.0;
        let refs: Vec<_> = values.iter().collect();
        let output = sample(&refs, 32, |v| *v);
        assert!(output.len() <= 32);
        assert!(output.contains(&&-100.0));
        assert!(output.contains(&&100.0));
    }
    #[test]
    fn indexed_35k_run_supports_bounded_cursor_queries() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let dir = root.join("systems/quant_replay_engine/runs/qrs_1790991887464");
        if !dir.join("events.ndjson").exists() {
            return;
        }
        let started = Instant::now();
        let repository = Repository::open(&dir).expect("existing Runner run");
        let open_ms = started.elapsed().as_millis();
        assert_eq!(repository.len(), 35_144);
        let started = Instant::now();
        let window = repository.window(None, None, 800, 25_000);
        let rows = repository
            .rows(Some("fill_created"), 0, 30, 25_000)
            .unwrap();
        let snapshot = repository.snapshot(25_000, None, false, 1.0).unwrap();
        let query_ms = started.elapsed().as_millis();
        assert!(window["prices"].as_array().unwrap().len() <= 800);
        assert!(window["pnl"].as_array().unwrap().len() <= 800);
        assert!(rows["rows"].as_array().unwrap().len() <= 30);
        assert_eq!(snapshot["cursor"], 25_000);
        println!("35,144 events: open {open_ms} ms; 800-point window + 30-row page + snapshot {query_ms} ms");
    }
}
