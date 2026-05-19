from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Iterable


DEFAULT_DATA_ROOT = Path("data/mon_usdc/v1")
DEFAULT_RUN_TAG = "20260510_86d"
DEFAULT_DATE_DIR = Path("date")
DEFAULT_DOCS_DIR = Path("docs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Rust MON/USDC V1 factor analysis and render the Markdown report."
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--run-tag", default=DEFAULT_RUN_TAG)
    parser.add_argument("--date-dir", type=Path, default=DEFAULT_DATE_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--force-derived", action="store_true")
    parser.add_argument("--no-derived-cache", action="store_true")
    parser.add_argument("--progress-interval", type=int, default=1000)
    parser.add_argument("--duckdb-threads", type=int, default=0, help=argparse.SUPPRESS)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_repo_path(path: str | Path) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return repo_root() / value


def output_paths(run_tag: str, date_dir: Path, docs_dir: Path) -> dict[str, Path]:
    return {
        "pool_summary": date_dir / f"mon_usdc_v1_pool_summary_{run_tag}.csv",
        "hourly_market": date_dir / f"mon_usdc_v1_hourly_market_features_{run_tag}.csv",
        "hourly_factor_tests": date_dir / f"mon_usdc_v1_hourly_factor_tests_{run_tag}.csv",
        "event_factor_tests": date_dir / f"mon_usdc_v1_event_factor_tests_{run_tag}.csv",
        "summary_json": date_dir / f"mon_usdc_v1_factor_analysis_summary_{run_tag}.json",
        "report": docs_dir / "markets" / "mon-usdc" / "v1-factor-analysis.md",
    }


def rust_binary(root: Path) -> Path:
    names = ["mon_usdc_factor_analysis.exe", "mon_usdc_factor_analysis"]
    for name in names:
        candidate = root / "target" / "release" / name
        if candidate.exists():
            return candidate
    return root / "target" / "release" / names[0]


def ensure_release_binary(root: Path) -> Path:
    binary = rust_binary(root)
    if binary.exists() and not release_binary_is_stale(root, binary):
        return binary
    if binary.exists():
        print("release mon_usdc_factor_analysis binary is stale; rebuilding it")
    else:
        print("release mon_usdc_factor_analysis binary not found; building it")
    subprocess.run(
        [
            "cargo",
            "build",
            "--release",
            "-p",
            "mon_usdc_research",
            "--bin",
            "mon_usdc_factor_analysis",
        ],
        cwd=root,
        check=True,
    )
    if not binary.exists() and binary.suffix == ".exe":
        alt = binary.with_suffix("")
        if alt.exists():
            return alt
    if not binary.exists():
        raise FileNotFoundError(f"release binary was not produced at {binary}")
    return binary


def release_binary_is_stale(root: Path, binary: Path) -> bool:
    binary_mtime = binary.stat().st_mtime
    source_roots = [
        root / "crates" / "mon_usdc_research",
        root / "crates" / "mon_usdc_collectors",
        root / "crates" / "finance_chain_core",
    ]
    candidates = [root / "Cargo.toml", root / "Cargo.lock"]
    for source_root in source_roots:
        candidates.append(source_root / "Cargo.toml")
        candidates.extend(source_root.rglob("*.rs"))
    return any(path.exists() and path.stat().st_mtime > binary_mtime for path in candidates)


def run_rust(args: argparse.Namespace) -> Path:
    root = repo_root()
    binary = ensure_release_binary(root)
    rust_args = [
        "--data-root",
        str(args.data_root),
        "--run-tag",
        args.run_tag,
        "--date-dir",
        str(args.date_dir),
        "--docs-dir",
        str(args.docs_dir),
        "--progress-interval",
        str(args.progress_interval),
    ]
    if args.force_derived:
        rust_args.append("--force-derived")
    if args.no_derived_cache:
        rust_args.append("--no-derived-cache")
    command = [str(binary), *rust_args]
    subprocess.run(command, cwd=root, check=True)
    return binary


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def f(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    if math.isfinite(number):
        return number
    return None


def i(value: object) -> int:
    number = f(value)
    return int(number) if number is not None else 0


def pct(value: object, digits: int = 2) -> str:
    number = f(value)
    if number is None:
        return "NA"
    return f"{number * 100:.{digits}f}%"


def num(value: object, digits: int = 2) -> str:
    number = f(value)
    if number is None:
        return "NA"
    sign = "-" if number < 0 else ""
    number = abs(number)
    if number >= 1_000_000_000:
        return f"{sign}{number / 1_000_000_000:.{digits}f}B"
    if number >= 1_000_000:
        return f"{sign}{number / 1_000_000:.{digits}f}M"
    if number >= 1_000:
        return f"{sign}{number / 1_000:.{digits}f}k"
    return f"{sign}{number:.{digits}f}"


def raw_num(value: object, digits: int = 4) -> str:
    number = f(value)
    if number is None:
        return "NA"
    return f"{number:.{digits}f}"


def short_hex(value: str, chars: int = 6) -> str:
    if not isinstance(value, str) or len(value) <= 2 * chars + 2:
        return str(value)
    return f"{value[: chars + 2]}...{value[-chars:]}"


def markdown_table(rows: Iterable[dict[str, object]], columns: list[tuple[str, str]]) -> str:
    materialized = list(rows)
    if not materialized:
        return "_No rows._"
    header = "| " + " | ".join(title for title, _ in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row.get(key, "")) for _, key in columns) + " |"
        for row in materialized
    ]
    return "\n".join([header, sep, *body])


def coverage_rows(summary: dict[str, object]) -> list[dict[str, str]]:
    coverage = summary["coverage"]
    prices = summary["price_coverage"]
    assert isinstance(coverage, dict)
    assert isinstance(prices, dict)
    return [
        {"metric": "raw pool_swap_logs rows", "value": f"{i(coverage['raw_swap_rows']):,}"},
        {"metric": "dedup swap rows", "value": f"{i(coverage['dedup_swap_rows']):,}"},
        {"metric": "clean swap rows", "value": f"{i(coverage['clean_swap_rows']):,}"},
        {"metric": "excluded dust/invalid swaps", "value": f"{i(coverage['excluded_swaps']):,}"},
        {"metric": "raw event_block_headers rows", "value": f"{i(coverage['raw_header_rows']):,}"},
        {"metric": "raw tx_receipts rows", "value": f"{i(coverage['raw_receipt_rows']):,}"},
        {
            "metric": "unique swap txs / blocks",
            "value": f"{i(coverage['unique_swap_txs']):,} / {i(coverage['unique_swap_blocks']):,}",
        },
        {
            "metric": "clean block window",
            "value": f"{i(coverage['clean_block_min'])}..{i(coverage['clean_block_max'])}",
        },
        {
            "metric": "clean time window",
            "value": f"{coverage['clean_start']} -> {coverage['clean_end']}",
        },
        {"metric": "calendar span", "value": f"{f(coverage['span_days']) or 0:.2f} days"},
        {
            "metric": "1m price rows",
            "value": (
                f"{i(prices['minute_rows']):,} "
                f"({i(prices['minute_observed']):,} observed, "
                f"{i(prices['minute_forward_fill']):,} ffill)"
            ),
        },
        {
            "metric": "hourly price rows",
            "value": (
                f"{i(prices['hourly_rows']):,} "
                f"({i(prices['hourly_observed']):,} observed, "
                f"{i(prices['hourly_forward_fill']):,} ffill)"
            ),
        },
    ]


def top_pool_rows(pool_summary: list[dict[str, str]], limit: int = 6) -> list[dict[str, str]]:
    rows = []
    for row in pool_summary[:limit]:
        rows.append(
            {
                "dex": row["dex_id"],
                "family": row["family"],
                "pool": short_hex(row["pool_address"]),
                "events": f"{i(row['clean_events']):,}",
                "quote": num(row["quote_volume"]),
                "share": pct(row.get("quote_volume_share")),
                "net": num(row["net_buy_base"]),
                "success": pct(row.get("receipt_success_rate")),
            }
        )
    return rows


def factor_rows(rows: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    selected = sorted(
        rows,
        key=lambda row: (abs(f(row.get("spearman")) or 0.0), i(row.get("n"))),
        reverse=True,
    )[:limit]
    return [
        {
            "factor": row["factor"],
            "target": row["target"],
            "n": f"{i(row['n']):,}",
            "spearman": raw_num(row.get("spearman")),
            "top_bottom": pct(row.get("high_minus_low")),
            "top_pos": pct(row.get("high_positive_rate")),
        }
        for row in selected
    ]


def exclusion_rows(summary: dict[str, object]) -> list[dict[str, str]]:
    rows = summary.get("exclusions", [])
    if not isinstance(rows, list):
        return []
    return [
        {"reason": str(row.get("reason", "")), "rows": f"{i(row.get('rows')):,}"}
        for row in rows
        if isinstance(row, dict)
    ]


def render_report(
    summary: dict[str, object],
    pool_summary: list[dict[str, str]],
    hourly_tests: list[dict[str, str]],
    event_tests: list[dict[str, str]],
) -> str:
    coverage = summary["coverage"]
    outputs = summary["outputs"]
    output_rows = summary["output_rows"]
    cache = summary.get("derived_cache", {})
    assert isinstance(coverage, dict)
    assert isinstance(outputs, dict)
    assert isinstance(output_rows, dict)
    assert isinstance(cache, dict)
    quality = "passed" if summary.get("quality_passed") else "needs_attention"
    hourly_tail_n = max(
        [i(row["n"]) for row in hourly_tests if row.get("target") == "fwd_24h"] or [0]
    )
    event_tail_n = max(
        [i(row["n"]) for row in event_tests if row.get("target") == "fwd_6h"] or [0]
    )
    data_root = summary["data_root"]
    run_tag = summary["run_tag"]
    executable_path = summary.get("executable_path", "NA")

    return f"""# MON/USDC V1 因子分析

状态: 2026-05-10。重计算逻辑已经迁移到 Rust release binary；Python 入口只负责自动构建/调用 release Rust、读取小型 summary/CSV，并渲染这份 Markdown。本报告扩到本地约 86-87 天三件套 raw 覆盖，只做 gross forward return 单因子研究，不输出交易规则，不做 ML。

复现命令:

```bash
python scripts/mon_usdc_v1_factor_analysis.py --data-root {data_root} --run-tag {run_tag} --force-derived
```

执行路径:

```text
{executable_path}
```

Derived cache: `{cache.get('status', 'NA')}`，schema=`{cache.get('schema_version', 'NA')}`，raw_hash=`{cache.get('raw_fingerprint_hash', 'NA')}`，raw_files=`{cache.get('raw_file_count', 'NA')}`。

输出:

```text
{outputs['pool_summary']}
{outputs['hourly_market']}
{outputs['hourly_factor_tests']}
{outputs['event_factor_tests']}
{outputs['summary_json']}
{outputs['report']}
```

## 1. 数据范围和质量

{markdown_table(coverage_rows(summary), [("指标", "metric"), ("值", "value")])}

质量状态: `{quality}`。`missing_event_headers={i(coverage['missing_event_headers']):,}`，`missing_receipts={i(coverage['missing_receipts']):,}`，`receipt_request_status_errors={i(coverage['receipt_request_status_errors']):,}`。链上失败 receipt 行 `{i(coverage['receipt_failure_rows']):,}`，保留在 gas/success rate 统计里。

清洗规则只排除 `base_abs<=0`、`quote_abs<=0`、`price_quote_per_base<=0` 或 removed 的 swap。排除明细:

{markdown_table(exclusion_rows(summary), [("原因", "reason"), ("行数", "rows")])}

## 2. 池子结构

{markdown_table(top_pool_rows(pool_summary), [("DEX", "dex"), ("Family", "family"), ("Pool", "pool"), ("Events", "events"), ("Quote Volume", "quote"), ("Share", "share"), ("Net Buy MON", "net"), ("Receipt Success", "success")])}

解释: Pancake v3、Uniswap v3 和两个 TraderJoe/LFJ v2.2 池都进入统一 `base=MON`、`quote=USDC` 口径。池子 CSV 同时保留 raw/clean 行数，方便检查 dust 排除是否只集中在特定池。

## 3. 小时级链路

小时级 panel 用 clean swap 聚合 VWAP、成交强度、方向流、rolling net flow、池/Dex quote share、HHI、活跃块、receipt success rate、priority fee、gas/base fee ratio 和 realized volatility。forward target 使用下一小时 VWAP 作为入场参考，避免同小时 flow 与当前小时 VWAP 共享信息；`fwd_24h` 最大可检验样本数为 `{hourly_tail_n:,}`。

绝对 Spearman 排名前列的小时级单因子测试:

{markdown_table(factor_rows(hourly_tests, 12), [("Factor", "factor"), ("Target", "target"), ("N", "n"), ("Spearman", "spearman"), ("Top-Bottom", "top_bottom"), ("Top >0", "top_pos")])}

## 4. 事件级链路

事件级 target 使用 1-minute VWAP 序列作为参考价，并从事件后的下一分钟 VWAP 开始计 forward return，避免事件所在分钟 VWAP 吃到当前事件本身；因子只来自当前事件字段: 方向、成交规模、signed quote flow、gas、priority fee、gas/base fee ratio 和同块事件密度。`fwd_6h` 最大可检验事件样本数为 `{event_tail_n:,}`。

绝对 Spearman 排名前列的事件级单因子测试:

{markdown_table(factor_rows(event_tests, 14), [("Factor", "factor"), ("Target", "target"), ("N", "n"), ("Spearman", "spearman"), ("Top-Bottom", "top_bottom"), ("Top >0", "top_pos")])}

## 5. 当前结论

1. 数据链路已经能从 raw swaps、event headers、receipts 直接生成池子汇总、小时级市场 panel 和事件级 forward-return tests。
2. 本轮只做 gross forward return 的单因子切分，尚未接入真实池费、tick liquidity、滑点和执行延迟，因此结果只用于候选现象筛选。
3. 小时级结果更偏 regime/流量/池结构解释，事件级结果更适合后续拆解方向、成交规模、gas 和同块拥挤的微观结构现象。
4. 下一步如果继续研究，应先做事件现象拆解和成本模型，而不是直接把这些行解释成可执行交易规则。

## 6. 产物行数

```text
pool_summary={output_rows['pool_summary']}
hourly_market={output_rows['hourly_market']}
hourly_factor_tests={output_rows['hourly_factor_tests']}
event_factor_tests={output_rows['event_factor_tests']}
```
"""


def main() -> None:
    args = parse_args()
    binary = run_rust(args)

    paths = output_paths(args.run_tag, args.date_dir, args.docs_dir)
    summary_path = resolve_repo_path(paths["summary_json"])
    with summary_path.open(encoding="utf-8") as handle:
        summary = json.load(handle)
    summary.setdefault("executable_path", str(binary))

    outputs = summary["outputs"]
    pool_summary = read_csv_rows(resolve_repo_path(outputs["pool_summary"]))
    hourly_tests = read_csv_rows(resolve_repo_path(outputs["hourly_factor_tests"]))
    event_tests = read_csv_rows(resolve_repo_path(outputs["event_factor_tests"]))

    report_path = resolve_repo_path(outputs["report"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_report(summary, pool_summary, hourly_tests, event_tests),
        encoding="utf-8",
    )
    print(f"wrote {outputs['report']}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
