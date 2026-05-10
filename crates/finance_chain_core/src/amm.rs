use anyhow::{Context, Result, bail};
use reqwest::blocking::Client;
use serde::Deserialize;
use serde_json::json;

use crate::dexscreener::PoolCandidate;
use crate::rpc::{RpcUrlPool, parse_hex_u64, rpc_call_from_pool};

pub const V2_SWAP_TOPIC: &str =
    "0xd78ad95fa46c994b6551d0da85fc275fe61363d4b8e3ee75a7d8e5be0c7f3b6a";
pub const V3_SWAP_TOPIC: &str =
    "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67";
pub const PANCAKE_V3_SWAP_TOPIC: &str =
    "0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83";
pub const LB_V22_SWAP_TOPIC: &str =
    "0xad7d6f97abf51ce18e17a38f4d70e975be9c0708474987bb3e26ad21bd93ca70";

const TOKEN0_SELECTOR: &str = "0x0dfe1681";
const TOKEN1_SELECTOR: &str = "0xd21220a7";
const GET_TOKEN_X_SELECTOR: &str = "0x05e8746d";
const GET_TOKEN_Y_SELECTOR: &str = "0xda10610c";
const DECIMALS_SELECTOR: &str = "0x313ce567";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SwapFamily {
    V2,
    V3,
    PancakeV3,
    LbV22,
}

impl SwapFamily {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::V2 => "v2",
            Self::V3 => "v3",
            Self::PancakeV3 => "pancake_v3",
            Self::LbV22 => "lb_v22",
        }
    }

    pub fn topic(self) -> &'static str {
        match self {
            Self::V2 => V2_SWAP_TOPIC,
            Self::V3 => V3_SWAP_TOPIC,
            Self::PancakeV3 => PANCAKE_V3_SWAP_TOPIC,
            Self::LbV22 => LB_V22_SWAP_TOPIC,
        }
    }

    pub fn from_topic(topic: &str) -> Option<Self> {
        if topic.eq_ignore_ascii_case(V2_SWAP_TOPIC) {
            Some(Self::V2)
        } else if topic.eq_ignore_ascii_case(V3_SWAP_TOPIC) {
            Some(Self::V3)
        } else if topic.eq_ignore_ascii_case(PANCAKE_V3_SWAP_TOPIC) {
            Some(Self::PancakeV3)
        } else if topic.eq_ignore_ascii_case(LB_V22_SWAP_TOPIC) {
            Some(Self::LbV22)
        } else {
            None
        }
    }
}

pub const SWAP_FAMILIES: [SwapFamily; 4] = [
    SwapFamily::V2,
    SwapFamily::V3,
    SwapFamily::PancakeV3,
    SwapFamily::LbV22,
];

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RpcSwapLog {
    pub address: String,
    pub topics: Vec<String>,
    pub data: String,
    pub block_number: String,
    pub block_timestamp: Option<String>,
    pub transaction_hash: String,
    pub transaction_index: String,
    pub log_index: String,
    #[serde(default)]
    pub removed: bool,
}

#[derive(Debug, Clone)]
pub struct PoolMetadata {
    pub pool: PoolCandidate,
    pub token0_address: String,
    pub token1_address: String,
    pub token0_decimals: u8,
    pub token1_decimals: u8,
    pub base_token_index: u8,
    pub quote_token_index: u8,
    pub base_symbol: String,
    pub quote_symbol: String,
    pub base_address: String,
    pub quote_address: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SignedAmount {
    sign: i8,
    magnitude: u128,
}

impl SignedAmount {
    pub fn from_parts(sign: i8, magnitude: u128) -> Self {
        let sign = if magnitude == 0 {
            0
        } else if sign < 0 {
            -1
        } else {
            1
        };
        Self { sign, magnitude }
    }

    pub fn from_i128(value: i128) -> Self {
        if value < 0 {
            Self::from_parts(-1, value.unsigned_abs())
        } else {
            Self::from_parts(1, value as u128)
        }
    }

    pub fn is_positive(self) -> bool {
        self.sign > 0
    }

    pub fn is_negative(self) -> bool {
        self.sign < 0
    }

    pub fn magnitude(self) -> u128 {
        self.magnitude
    }

    pub fn raw_string(self) -> String {
        if self.sign < 0 {
            format!("-{}", self.magnitude)
        } else {
            self.magnitude.to_string()
        }
    }

    pub fn signed_decimal_string(self, decimals: u8) -> String {
        if self.sign < 0 {
            format!("-{}", format_unsigned_decimal(self.magnitude, decimals))
        } else {
            format_unsigned_decimal(self.magnitude, decimals)
        }
    }

    pub fn abs_decimal_string(self, decimals: u8) -> String {
        format_unsigned_decimal(self.magnitude, decimals)
    }

    pub fn scaled_abs_f64(self, decimals: u8) -> f64 {
        self.magnitude as f64 / 10f64.powi(i32::from(decimals))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SwapDeltas {
    pub amount0_delta_raw: SignedAmount,
    pub amount1_delta_raw: SignedAmount,
    pub sqrt_price_x96: Option<String>,
    pub liquidity_raw: Option<String>,
    pub tick: Option<String>,
}

pub fn resolve_pool_metadata(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    pool: &PoolCandidate,
    base_token: &str,
    quote_token: &str,
    base_symbol: &str,
    quote_symbol: &str,
) -> Result<PoolMetadata> {
    let (token0_address, token1_address) = resolve_pool_token_addresses(client, rpc_urls, pool)?;
    let token0_decimals = eth_call_u8(client, rpc_urls, &token0_address, DECIMALS_SELECTOR)
        .with_context(|| format!("failed decimals() for token0 {token0_address}"))?;
    let token1_decimals = eth_call_u8(client, rpc_urls, &token1_address, DECIMALS_SELECTOR)
        .with_context(|| format!("failed decimals() for token1 {token1_address}"))?;

    let token0_lower = token0_address.to_ascii_lowercase();
    let token1_lower = token1_address.to_ascii_lowercase();
    let base_lower = base_token.to_ascii_lowercase();
    let quote_lower = quote_token.to_ascii_lowercase();
    let base_token_index = if token0_lower == base_lower {
        0
    } else if token1_lower == base_lower {
        1
    } else {
        bail!(
            "pool {} token0/token1 do not include base token {base_token}: {token0_address}/{token1_address}",
            pool.pair_address
        );
    };
    let quote_token_index = if token0_lower == quote_lower {
        0
    } else if token1_lower == quote_lower {
        1
    } else {
        bail!(
            "pool {} token0/token1 do not include quote token {quote_token}: {token0_address}/{token1_address}",
            pool.pair_address
        );
    };

    Ok(PoolMetadata {
        pool: pool.clone(),
        token0_address,
        token1_address,
        token0_decimals,
        token1_decimals,
        base_token_index,
        quote_token_index,
        base_symbol: base_symbol.to_string(),
        quote_symbol: quote_symbol.to_string(),
        base_address: base_token.to_ascii_lowercase(),
        quote_address: quote_token.to_ascii_lowercase(),
    })
}

pub fn parse_log_block_number(log: &RpcSwapLog) -> Result<u64> {
    parse_hex_u64(&log.block_number)
}

pub fn parse_log_transaction_index(log: &RpcSwapLog) -> Result<u64> {
    parse_hex_u64(&log.transaction_index)
}

pub fn parse_log_index(log: &RpcSwapLog) -> Result<u64> {
    parse_hex_u64(&log.log_index)
}

pub fn parse_swap_deltas(family: SwapFamily, data: &str) -> Result<SwapDeltas> {
    match family {
        SwapFamily::V2 => parse_v2_deltas(data),
        SwapFamily::V3 | SwapFamily::PancakeV3 => parse_v3_like_deltas(data),
        SwapFamily::LbV22 => parse_lb_v22_deltas(data),
    }
}

pub fn direction_for_base_delta(base_delta: SignedAmount) -> &'static str {
    if base_delta.is_positive() {
        "sell_base"
    } else if base_delta.is_negative() {
        "buy_base"
    } else {
        "unknown"
    }
}

pub fn price_quote_per_base(
    base_abs_raw: u128,
    base_decimals: u8,
    quote_abs_raw: u128,
    quote_decimals: u8,
) -> Option<String> {
    if base_abs_raw == 0 {
        return None;
    }
    let base = base_abs_raw as f64 / 10f64.powi(i32::from(base_decimals));
    let quote = quote_abs_raw as f64 / 10f64.powi(i32::from(quote_decimals));
    Some(format!("{:.18}", quote / base))
}

pub fn topic_to_address(topic: &str) -> Result<String> {
    let topic = topic.trim_start_matches("0x");
    if topic.len() != 64 {
        bail!("invalid indexed address topic: 0x{topic}");
    }
    Ok(format!("0x{}", &topic[24..]).to_ascii_lowercase())
}

fn resolve_pool_token_addresses(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    pool: &PoolCandidate,
) -> Result<(String, String)> {
    let token0_result = eth_call_address(client, rpc_urls, &pool.pair_address, TOKEN0_SELECTOR);
    let token1_result = eth_call_address(client, rpc_urls, &pool.pair_address, TOKEN1_SELECTOR);
    match (token0_result, token1_result) {
        (Ok(token0), Ok(token1)) => return Ok((token0, token1)),
        (token0_result, token1_result) => {
            let token0_error = token0_result.err();
            let token1_error = token1_result.err();
            let token_x =
                eth_call_address(client, rpc_urls, &pool.pair_address, GET_TOKEN_X_SELECTOR)
                    .with_context(|| {
                        let token0_context = token0_error
                            .as_ref()
                            .map(|error| format!("; token0() failed first: {error:#}"))
                            .unwrap_or_default();
                        format!(
                            "failed getTokenX() for {}{token0_context}",
                            pool.pair_address
                        )
                    })?;
            let token_y =
                eth_call_address(client, rpc_urls, &pool.pair_address, GET_TOKEN_Y_SELECTOR)
                    .with_context(|| {
                        let token1_context = token1_error
                            .as_ref()
                            .map(|error| format!("; token1() failed first: {error:#}"))
                            .unwrap_or_default();
                        format!(
                            "failed getTokenY() for {}{token1_context}",
                            pool.pair_address
                        )
                    })?;
            Ok((token_x, token_y))
        }
    }
}

fn eth_call_address(
    client: &Client,
    rpc_urls: &RpcUrlPool,
    to: &str,
    selector: &str,
) -> Result<String> {
    let value: String = rpc_call_from_pool(
        client,
        rpc_urls,
        "eth_call",
        json!([{ "to": to, "data": selector }, "latest"]),
    )?;
    decode_address_word(&value)
}

fn eth_call_u8(client: &Client, rpc_urls: &RpcUrlPool, to: &str, selector: &str) -> Result<u8> {
    let value: String = rpc_call_from_pool(
        client,
        rpc_urls,
        "eth_call",
        json!([{ "to": to, "data": selector }, "latest"]),
    )?;
    let value = parse_u256_to_u128(value.trim_start_matches("0x"))?;
    if value > u8::MAX as u128 {
        bail!("eth_call value does not fit u8: {value}");
    }
    Ok(value as u8)
}

fn decode_address_word(value: &str) -> Result<String> {
    let word = value.trim_start_matches("0x");
    if word.len() < 64 {
        bail!("eth_call address result is shorter than 32 bytes: {value}");
    }
    Ok(format!("0x{}", &word[word.len() - 40..]).to_ascii_lowercase())
}

fn parse_v2_deltas(data: &str) -> Result<SwapDeltas> {
    let chunks = data_chunks(data)?;
    if chunks.len() < 4 {
        bail!("v2 swap data has fewer than 4 words: {data}");
    }
    let amount0_in = parse_u256_to_u128(chunks[0])?;
    let amount1_in = parse_u256_to_u128(chunks[1])?;
    let amount0_out = parse_u256_to_u128(chunks[2])?;
    let amount1_out = parse_u256_to_u128(chunks[3])?;
    Ok(SwapDeltas {
        amount0_delta_raw: u128_diff_to_signed(amount0_in, amount0_out),
        amount1_delta_raw: u128_diff_to_signed(amount1_in, amount1_out),
        sqrt_price_x96: None,
        liquidity_raw: None,
        tick: None,
    })
}

fn parse_v3_like_deltas(data: &str) -> Result<SwapDeltas> {
    let chunks = data_chunks(data)?;
    if chunks.len() < 5 {
        bail!("v3 swap data has fewer than 5 words: {data}");
    }
    Ok(SwapDeltas {
        amount0_delta_raw: parse_i256(chunks[0])?,
        amount1_delta_raw: parse_i256(chunks[1])?,
        sqrt_price_x96: Some(parse_u256_decimal(chunks[2])?),
        liquidity_raw: Some(parse_u256_decimal(chunks[3])?),
        tick: Some(parse_i256(chunks[4])?.raw_string()),
    })
}

fn parse_lb_v22_deltas(data: &str) -> Result<SwapDeltas> {
    let chunks = data_chunks(data)?;
    if chunks.len() < 6 {
        bail!("lb v2.2 swap data has fewer than 6 words: {data}");
    }
    let (amount_x_in, amount_y_in) = parse_packed_x_y_amounts(chunks[1])?;
    let (amount_x_out, amount_y_out) = parse_packed_x_y_amounts(chunks[2])?;
    Ok(SwapDeltas {
        amount0_delta_raw: u128_diff_to_signed(amount_x_in, amount_x_out),
        amount1_delta_raw: u128_diff_to_signed(amount_y_in, amount_y_out),
        sqrt_price_x96: None,
        liquidity_raw: None,
        tick: Some(parse_u256_decimal(chunks[0])?),
    })
}

fn data_chunks(data: &str) -> Result<Vec<&str>> {
    let data = data.trim_start_matches("0x");
    if data.len() % 64 != 0 {
        bail!("data length is not a multiple of 32 bytes: 0x{data}");
    }
    Ok(data
        .as_bytes()
        .chunks(64)
        .map(std::str::from_utf8)
        .collect::<std::result::Result<Vec<_>, _>>()?)
}

fn parse_packed_x_y_amounts(word: &str) -> Result<(u128, u128)> {
    let bytes = hex_word_to_bytes(word)?;
    let mut amount_y = [0u8; 16];
    let mut amount_x = [0u8; 16];
    amount_y.copy_from_slice(&bytes[..16]);
    amount_x.copy_from_slice(&bytes[16..]);
    Ok((u128::from_be_bytes(amount_x), u128::from_be_bytes(amount_y)))
}

fn parse_i256(word: &str) -> Result<SignedAmount> {
    let bytes = hex_word_to_bytes(word)?;
    let negative = bytes[0] & 0x80 != 0;
    if !negative {
        Ok(SignedAmount::from_parts(1, u256_bytes_to_u128(&bytes)?))
    } else {
        let mut magnitude = [0u8; 32];
        for (index, byte) in bytes.iter().enumerate() {
            magnitude[index] = !byte;
        }
        add_one_be(&mut magnitude);
        Ok(SignedAmount::from_parts(
            -1,
            u256_bytes_to_u128(&magnitude)?,
        ))
    }
}

fn parse_u256_to_u128(word: &str) -> Result<u128> {
    let bytes = hex_word_to_bytes(word)?;
    u256_bytes_to_u128(&bytes)
}

fn u256_bytes_to_u128(bytes: &[u8; 32]) -> Result<u128> {
    if bytes[..16].iter().any(|byte| *byte != 0) {
        bail!("uint256 does not fit u128: 0x{}", bytes_to_hex(bytes));
    }
    let mut low = [0u8; 16];
    low.copy_from_slice(&bytes[16..]);
    Ok(u128::from_be_bytes(low))
}

fn hex_word_to_bytes(word: &str) -> Result<[u8; 32]> {
    let word = word.trim_start_matches("0x");
    if word.len() != 64 {
        bail!("expected 32-byte word, got 0x{word}");
    }
    let mut bytes = [0u8; 32];
    for index in 0..32 {
        bytes[index] = u8::from_str_radix(&word[index * 2..index * 2 + 2], 16)
            .with_context(|| format!("invalid hex word: 0x{word}"))?;
    }
    Ok(bytes)
}

fn add_one_be(bytes: &mut [u8; 32]) {
    for byte in bytes.iter_mut().rev() {
        let (next, carry) = byte.overflowing_add(1);
        *byte = next;
        if !carry {
            break;
        }
    }
}

fn u128_diff_to_signed(left: u128, right: u128) -> SignedAmount {
    if left >= right {
        SignedAmount::from_parts(1, left - right)
    } else {
        SignedAmount::from_parts(-1, right - left)
    }
}

fn parse_u256_decimal(word: &str) -> Result<String> {
    let bytes = hex_word_to_bytes(word)?;
    let mut digits = vec![0u8];
    for byte in bytes {
        multiply_decimal_digits(&mut digits, 256);
        add_decimal_number(&mut digits, u16::from(byte));
    }
    while digits.len() > 1 && digits[0] == 0 {
        digits.remove(0);
    }
    Ok(digits
        .into_iter()
        .map(|digit| char::from(b'0' + digit))
        .collect())
}

fn multiply_decimal_digits(digits: &mut Vec<u8>, multiplier: u16) {
    let mut carry = 0u16;
    for digit in digits.iter_mut().rev() {
        let value = u16::from(*digit) * multiplier + carry;
        *digit = (value % 10) as u8;
        carry = value / 10;
    }
    while carry > 0 {
        digits.insert(0, (carry % 10) as u8);
        carry /= 10;
    }
}

fn add_decimal_number(digits: &mut Vec<u8>, addend: u16) {
    let mut carry = addend;
    for digit in digits.iter_mut().rev() {
        let value = u16::from(*digit) + carry;
        *digit = (value % 10) as u8;
        carry = value / 10;
        if carry == 0 {
            break;
        }
    }
    while carry > 0 {
        digits.insert(0, (carry % 10) as u8);
        carry /= 10;
    }
}

fn format_unsigned_decimal(value: u128, decimals: u8) -> String {
    if decimals == 0 {
        return value.to_string();
    }
    let scale = 10u128.pow(u32::from(decimals));
    let whole = value / scale;
    let frac = value % scale;
    if frac == 0 {
        return whole.to_string();
    }
    let mut frac_text = format!("{:0width$}", frac, width = decimals as usize);
    while frac_text.ends_with('0') {
        frac_text.pop();
    }
    format!("{whole}.{frac_text}")
}

fn bytes_to_hex(bytes: &[u8; 32]) -> String {
    bytes
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn word(value: u128) -> String {
        format!("{value:064x}")
    }

    fn signed_word(value: i128) -> String {
        if value >= 0 {
            word(value as u128)
        } else {
            let mut bytes = [0u8; 32];
            bytes[16..].copy_from_slice(&value.unsigned_abs().to_be_bytes());
            for byte in &mut bytes {
                *byte = !*byte;
            }
            add_one_be(&mut bytes);
            bytes_to_hex(&bytes)
        }
    }

    fn packed_xy(amount_x: u128, amount_y: u128) -> String {
        format!("{amount_y:032x}{amount_x:032x}")
    }

    #[test]
    fn decodes_v2_swap_delta() {
        let data = format!(
            "0x{}{}{}{}",
            word(1_000_000_000_000_000_000),
            word(0),
            word(0),
            word(50_000_000)
        );
        let deltas = parse_swap_deltas(SwapFamily::V2, &data).unwrap();
        assert_eq!(
            deltas.amount0_delta_raw,
            SignedAmount::from_i128(1_000_000_000_000_000_000)
        );
        assert_eq!(
            deltas.amount1_delta_raw,
            SignedAmount::from_i128(-50_000_000)
        );
    }

    #[test]
    fn decodes_uniswap_v3_swap_delta() {
        let data = format!(
            "0x{}{}{}{}{}",
            signed_word(-2_000_000_000_000_000_000),
            signed_word(68_000_000),
            word(42),
            word(123),
            signed_word(-10)
        );
        let deltas = parse_swap_deltas(SwapFamily::V3, &data).unwrap();
        assert_eq!(
            deltas.amount0_delta_raw,
            SignedAmount::from_i128(-2_000_000_000_000_000_000)
        );
        assert_eq!(
            deltas.amount1_delta_raw,
            SignedAmount::from_i128(68_000_000)
        );
        assert_eq!(deltas.sqrt_price_x96.as_deref(), Some("42"));
        assert_eq!(deltas.liquidity_raw.as_deref(), Some("123"));
        assert_eq!(deltas.tick.as_deref(), Some("-10"));
    }

    #[test]
    fn decodes_pancake_v3_extended_swap_topic_using_first_five_words() {
        let data = format!(
            "0x{}{}{}{}{}{}{}",
            signed_word(1_500_000_000_000_000_000),
            signed_word(-51_000_000),
            word(77),
            word(456),
            signed_word(15),
            word(999),
            word(1_000)
        );
        let deltas = parse_swap_deltas(SwapFamily::PancakeV3, &data).unwrap();
        assert_eq!(
            deltas.amount0_delta_raw,
            SignedAmount::from_i128(1_500_000_000_000_000_000)
        );
        assert_eq!(
            deltas.amount1_delta_raw,
            SignedAmount::from_i128(-51_000_000)
        );
        assert_eq!(deltas.sqrt_price_x96.as_deref(), Some("77"));
        assert_eq!(deltas.liquidity_raw.as_deref(), Some("456"));
        assert_eq!(deltas.tick.as_deref(), Some("15"));
    }

    #[test]
    fn decodes_lb_v22_packed_swap_delta() {
        let data = format!(
            "0x{}{}{}{}{}{}",
            word(8_388_600),
            packed_xy(1_250_000_000_000_000_000, 0),
            packed_xy(0, 41_250_000),
            word(100),
            packed_xy(3_000_000_000_000_000, 99_000),
            packed_xy(1_000_000_000_000_000, 33_000)
        );
        let deltas = parse_swap_deltas(SwapFamily::LbV22, &data).unwrap();
        assert_eq!(
            deltas.amount0_delta_raw,
            SignedAmount::from_i128(1_250_000_000_000_000_000)
        );
        assert_eq!(
            deltas.amount1_delta_raw,
            SignedAmount::from_i128(-41_250_000)
        );
        assert_eq!(deltas.sqrt_price_x96, None);
        assert_eq!(deltas.liquidity_raw, None);
        assert_eq!(deltas.tick.as_deref(), Some("8388600"));
    }

    #[test]
    fn maps_lb_v22_swap_topic() {
        assert_eq!(
            SwapFamily::from_topic(LB_V22_SWAP_TOPIC),
            Some(SwapFamily::LbV22)
        );
        assert_eq!(SwapFamily::LbV22.topic(), LB_V22_SWAP_TOPIC);
    }

    #[test]
    fn classifies_mon_usdc_direction_from_pool_base_delta() {
        assert_eq!(
            direction_for_base_delta(SignedAmount::from_i128(1)),
            "sell_base"
        );
        assert_eq!(
            direction_for_base_delta(SignedAmount::from_i128(-1)),
            "buy_base"
        );
        assert_eq!(
            direction_for_base_delta(SignedAmount::from_i128(0)),
            "unknown"
        );
    }

    #[test]
    fn computes_quote_per_base_price() {
        let price = price_quote_per_base(2_000_000_000_000_000_000, 18, 68_000, 6).unwrap();
        assert_eq!(price, "0.034000000000000002");
    }

    #[test]
    fn formats_decimals_without_chog_specific_names() {
        assert_eq!(
            SignedAmount::from_i128(-1_230_000_000_000_000_000).signed_decimal_string(18),
            "-1.23"
        );
        assert_eq!(
            SignedAmount::from_i128(68_000).abs_decimal_string(6),
            "0.068"
        );
    }
}
