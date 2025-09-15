#################################################################
# ExpertOption runner (Demo/Real) with a single, clean auth flow
# Example TEST CMD (TOKEN-only, Expert Option)
#################################################################
# ======================
# python test1.py
# ======================
import asyncio
import time
import threading
from typing import Optional, Dict, Any, Tuple, List
import pandas as pd
from loguru import logger
from rich import print as rprint
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.table import Table

# ======================
# Color tokens for console
# ======================
ENDC = "[white]"
PURPLE = "[purple]"
DARK_GRAY = "[bright_black]"
OKCYAN = "[steel_blue1]"
lg = "[green3]"
r = "[red]"
dr = "[dark_red]"
dg = "[spring_green4]"
dg2 = "[dark_green]"
bl = "[blue]"
g = "[green]"
w = "[white]"
cy = "[cyan]"
ye = "[yellow]"
yl = "[#FFD700]"
orange = "[dark_orange3]"
Bold_orange = "[bold orange1]"
Bold_green = "[bold green]"
info = g + "[" + w + "i" + g + "]" + ENDC
attempt = g + "[" + w + "+" + g + "]" + ENDC
sleep = bl + "[" + w + "*" + bl + "]" + ENDC
error = g + "[" + r + "!" + g + "]" + ENDC
success = w + "(" + lg + "*" + w + ")" + ENDC
INPUT = lg + "(" + cy + "~" + lg + ")" + ENDC
warning = yl + "(" + w + "!" + yl + ")" + ENDC
wait = yl + "(" + w + "●" + yl + ")" + ENDC
win = w + "[" + lg + "✓" + w + "]" + ENDC
loss = w + "[" + r + "x" + w + "]" + ENDC
draw = w + "[" + OKCYAN + "≈" + w + "]" + ENDC

# API imports
from api_expert import (
    AsyncExpertOptionClient,
    load_config, save_config, save_session, get_token,
)
from api_expert.constants import TIMEFRAMES, get_asset_symbol
from api_expert.models import OrderDirection
from api_expert.utils import format_timeframe

# Helpers
# ========================
# Assets Table
# ========================
def print_assets_table(
    assets: Dict[str, Dict[str, Any]],
    *,
    only_open: bool = False,
    sort_by_payout: bool = True,
    top: int = 0
):
    """
    assets comes from client.get_available_assets():
    - keys are sanitized symbols,
    - values are dicts with: id, symbol, name, type, payout, is_otc, is_open, available_timeframes...
    """
    console = Console()
    table = Table(title=f"{PURPLE}Available Assets and Payouts{ENDC}", show_lines=True)
    table.add_column(f"{cy}ID{ENDC}", justify="right", no_wrap=True)
    table.add_column(f"{cy}Symbol{ENDC}", justify="left", no_wrap=True)
    table.add_column(f"{g}Name{ENDC}")
    table.add_column(f"{PURPLE}Type{ENDC}")
    table.add_column(f"{ye}Payout %{ENDC}", justify="right")
    table.add_column(f"{r}OTC{ENDC}")
    table.add_column(f"{ENDC}Open{ENDC}")
    table.add_column(f"{ENDC}Timeframes{ENDC}")

    rows = list(assets.values())
    if only_open:
        rows = [v for v in rows if v.get("is_open") and (v.get("payout", 0) or 0) > 0]
    if not rows:
        rprint(Panel("[yellow]No assets matched the current filter.[/yellow]", title="[i] Assets Filter Result"))
        return
    if sort_by_payout:
        rows.sort(key=lambda x: x.get("payout", 0), reverse=True)
    if top > 0:
        rows = rows[:top]

    for info in rows:
        aid = info.get("id", "--")
        symbol = get_asset_symbol(int(aid)) if isinstance(aid, int) else None
        symbol = symbol or info.get("symbol", "UNKNOWN")
        name = info.get("name", "--")
        tfs = info.get("available_timeframes", []) or []
        tfs_str = ", ".join(format_timeframe(t) for t in tfs) if tfs else "N/A"
        table.add_row(
            f"{cy}{aid}{ENDC}",
            f"{cy}{symbol}{ENDC}",
            f"{g}{name}{ENDC}",
            f"{PURPLE}{info.get('type','--')}{ENDC}",
            f"{ye}{info.get('payout','--')}{ENDC}",
            f"{r}Yes{ENDC}" if info.get("is_otc") else f"{ENDC}No{ENDC}",
            f"{g}Yes{ENDC}" if info.get("is_open") else f"{ENDC}No{ENDC}",
            f"{ENDC}{tfs_str}{ENDC}",
        )
    console.print(table)

# ========================
# Candles Table
# ========================
def print_candles_table(candles_df: pd.DataFrame, asset: str, timeframe: str):
    console = Console()
    table = Table(title=f"{PURPLE}Candles for {asset} ({timeframe}){ENDC}", show_lines=True)
    table.add_column(f"{cy}Timestamp{ENDC}", justify="left")
    table.add_column(f"{g}Open{ENDC}", justify="right")
    table.add_column(f"{ye}High{ENDC}", justify="right")
    table.add_column(f"{r}Low{ENDC}", justify="right")
    table.add_column(f"{ENDC}Close{ENDC}", justify="right")
    table.add_column(f"{PURPLE}Volume{ENDC}", justify="right")
    for idx, row in candles_df.iterrows():
        table.add_row(
            f"{cy}{idx.strftime('%Y-%m-%d %H:%M:%S')}{ENDC}",
            f"{g}{row['open']:.5f}{ENDC}",
            f"{ye}{row['high']:.5f}{ENDC}",
            f"{r}{row['low']:.5f}{ENDC}",
            f"{ENDC}{row['close']:.5f}{ENDC}",
            f"{PURPLE}{(row['volume'] or 0):.2f}{ENDC}",
        )
    console.print(table)

# ========================
# Print one live (non-blocking) bar
# ========================
async def try_print_one_live_bar(client: AsyncExpertOptionClient, asset_id: int, asset_symbol: str, timeframe: int):
    try:
        candles = await client.get_candles(asset_id, timeframe, count=1)
        if not candles:
            return
        candle = candles[0]
        rprint(
            f"{info} {DARK_GRAY}Live bar: {cy}{asset_symbol}{ENDC} @ {format_timeframe(timeframe)} "
            f"| O={g}{candle.open:.5f}{ENDC} H={ye}{candle.high:.5f}{ENDC} "
            f"L={r}{candle.low:.5f}{ENDC} C={ENDC}{candle.close:.5f}{ENDC}"
        )
    except Exception as e:
        logger.warning(f"Failed to fetch live bar for {asset_symbol}: {e}")

# ========================
# Await order result
# ========================
async def check_win_task(client: AsyncExpertOptionClient, order_id: str) -> None:
    try:
        profit, status = await client.check_win(order_id)
        color_code = {
            "win": f"{g}WIN{ENDC}",
            "loss": f"{r}LOSS{ENDC}",
            "draw": f"{OKCYAN}DRAW{ENDC}",
            "cancelled": f"{ye}CANCELLED{ENDC}",
        }.get(status.lower(), f"{w}{status.upper()}{ENDC}")
        icon = {
            "win": win,
            "loss": loss,
            "draw": draw,
            "cancelled": wait,
        }.get(status.lower(), wait)
        profit_color = g if profit > 0 else r if profit < 0 else OKCYAN
        profit_val = f"{profit_color}${profit:.2f}{ENDC}"
        order_result = await client.check_order_result(order_id)
        completion_time = (
            order_result.expires_at.strftime("%Y-%m-%d %H:%M:%S") if order_result and order_result.expires_at else "N/A"
        )
        asset_sym = get_asset_symbol(order_result.asset_id) if order_result and order_result.asset_id else None
        asset_sym = asset_sym or (order_result.asset if order_result else "UNKNOWN")
        server_id = (order_result.server_id if order_result and order_result.server_id else "N/A")
        asset_id = (order_result.asset_id if order_result and order_result.asset_id else "N/A")
        open_price = f"{order_result.open_price:.5f}" if order_result and order_result.open_price else "N/A"
        close_price = f"{order_result.close_price:.5f}" if order_result and order_result.close_price else "N/A"
        direction = order_result.direction.value.upper() if order_result and order_result.direction else "N/A"
        panel_content = (
            f"{DARK_GRAY}Order ID: {ye}{order_id}{ENDC}\n"
            f"{DARK_GRAY}Server ID: {ye}{server_id}{ENDC}\n"
            f"{DARK_GRAY}Asset: {cy}{asset_sym} ({asset_id}){ENDC}\n"
            f"{DARK_GRAY}Direction: {cy}{direction}{ENDC}\n"
            f"{DARK_GRAY}Result: {icon} {color_code}\n"
            f"{DARK_GRAY}Profit/Loss: {profit_val}\n"
            f"{DARK_GRAY}Open Price: {g}{open_price}{ENDC}\n"
            f"{DARK_GRAY}Close Price: {g}{close_price}{ENDC}\n"
            f"{DARK_GRAY}Completion Time: {ye}{completion_time}{ENDC}"
        )
        logger.info(
            f"Trade {order_id} finished with result: "
            f"{{'result': '{status}', 'profit': {profit}, "
            f"'details': {{'id': '{order_id}', 'server_id': '{server_id}', "
            f"'asset': '{asset_sym}', 'asset_id': {asset_id}, 'direction': '{direction}', "
            f"'open_price': '{open_price}', 'close_price': '{close_price}'}}}}"
        )
        rprint(
            Panel(
                panel_content,
                title=f"{g}Trade Result{ENDC}",
                border_style="bright_green" if status.lower() == "win" else "red" if status.lower() == "loss" else "yellow",
            )
        )
    except Exception as e:
        logger.error(f"Failed to check win result for order {order_id}: {e}", exc_info=True)
        rprint(Panel(f"[red]Exception:[/red] {str(e)}", title="Trade Result Error", border_style="red"))

# ========================
# Choose best asset by payout for timeframe
# ========================
def choose_best_asset(assets: Dict[str, Dict[str, Any]], timeframe: str) -> Optional[Tuple[int, str, float]]:
    tf_seconds = TIMEFRAMES.get(timeframe)
    if not tf_seconds:
        return None
    best = None  # (payout, asset_id)
    for info in assets.values():
        try:
            if not info.get("is_open"):
                continue
            tfs = info.get("available_timeframes", []) or []
            if tf_seconds not in tfs:
                continue
            payout = float(info.get("payout", 0) or 0)
            if payout <= 0:
                continue
            aid = int(info.get("id"))
            if best is None or payout > best[0]:
                best = (payout, aid)
        except Exception:
            continue
    if not best:
        return None
    payout, aid = best
    return aid, timeframe, payout

# ======================
# Main 
# ======================
async def main():
    console = Console()
    client: Optional[AsyncExpertOptionClient] = None
    try:
        # Step 1: Load or ask for credentials
        cfg = load_config()
        email = cfg.get("email", "") or Prompt.ask(f"{INPUT} {DARK_GRAY}Enter {cy}ExpertOption{DARK_GRAY} Email{ENDC}{yl}")
        password = cfg.get("password", "") or Prompt.ask(f"{INPUT} {DARK_GRAY}Enter {cy}ExpertOption{DARK_GRAY} Password{ENDC}{yl}", password=True)
        if cfg.get("email") and cfg.get("password"):
            change = Prompt.ask(f'{INPUT} {DARK_GRAY}Change saved credentials for {cy}{cfg["email"]}{DARK_GRAY}[{g}y{DARK_GRAY}]?{ENDC}').strip().lower()
            if change == "y":
                email = Prompt.ask(f"{INPUT} {DARK_GRAY}Enter {cy}ExpertOption{DARK_GRAY} Email{ENDC}{yl}")
                password = Prompt.ask(f"{INPUT} {DARK_GRAY}Enter {cy}ExpertOption{DARK_GRAY} Password{ENDC}{yl}", password=True)
        cfg["email"] = email
        cfg["password"] = password
        save_config(cfg)

        # Step 2: Choose account type
        choice = Prompt.ask(f"{INPUT} {DARK_GRAY}Choose account type {w}({Bold_green}1{w} = REAL, {Bold_green}2{w} = DEMO){ENDC}")
        is_demo = (choice != "1")

        ok, session = await get_token(is_demo=is_demo, email=email, password=password)
        if not ok or not isinstance(session, dict) or not session.get("token"):
            console.print(f"{error} {DARK_GRAY}Failed to obtain token.{ENDC}")
            return
        token = session["token"]
        console.print(f"{info} {DARK_GRAY}Using token: {token[:12]}... (demo={is_demo}){ENDC}")
        logger.info(f"Token acquired for {'Demo' if is_demo else 'Real'} account")
        save_session({
            "token": token,
            "is_demo": 1 if is_demo else 0,
            "ts": int(time.time()),
        })

        # Step 3: Connect once
        client = AsyncExpertOptionClient(
            token=token,
            is_demo=is_demo,
            persistent_connection=False,
            enable_logging=True,
        )
        if not await client.connect():
            console.print(f"{error} {DARK_GRAY}Failed to connect to ExpertOption server.{ENDC}")
            return
        rprint(Panel(f"{OKCYAN}Connected to {'Demo' if is_demo else 'Real'} account!{ENDC}", title=f"{g}Status{ENDC}"))
        logger.info("Connected successfully")

        # Step 4: Main loop (balance → assets → candles → live → test orders)
        last_assets_refresh = 0.0
        refresh_interval = 60.0
        assets_cache: Dict[str, Dict[str, Any]] = {}
        while True:
            try:
                if not getattr(client, "is_connected", False):
                    logger.info(f"{bl}Reconnecting...{ENDC}")
                    if not await client.connect():
                        logger.error("Connection failed, retrying...")
                        await asyncio.sleep(10)
                        continue
                    rprint(Panel(f"{OKCYAN}Reconnected!{ENDC}", title=f"{g}Status{ENDC}"))

                # Account info
                balance = await client.get_balance()
                bal_value = getattr(balance, "balance", 0.0)
                rprint(
                    Panel(
                        f"{info} {DARK_GRAY}Balance: {g}{bal_value:.2f} {balance.currency}{ENDC}\n"
                        f"{info} {DARK_GRAY}Demo: {ye}{balance.is_demo}{ENDC}\n"
                        f"{info} {DARK_GRAY}Uid: {g}{getattr(client, 'uid', '--')}{ENDC}",
                        title=f"{info} {PURPLE}Account Info{ENDC}",
                    )
                )

                now = time.time()
                if now - last_assets_refresh >= refresh_interval or not assets_cache:  # تصحيح المتغيرات
                    assets_cache = await client.get_available_assets()
                    print_assets_table(assets_cache, only_open=True, top=20)
                    last_assets_refresh = now  # تصحيح التحديث

                # Choose best 1m asset
                choice = choose_best_asset(assets_cache, "1m")
                if not choice:
                    rprint(
                        Panel(
                            "[yellow]No candidate asset with payout>0 and 1m found.[/yellow]\n"
                            "Check available_timeframes mapping & market open flags.",
                            title="[i] Selection",
                        )
                    )
                    await asyncio.sleep(20)
                    continue

                asset_id, tf_str, payout = choice
                asset_sym = get_asset_symbol(asset_id) or next(
                    (v.get("symbol") for v in assets_cache.values() if v.get("id") == asset_id),
                    str(asset_id),
                )
                rprint(f"{info} {DARK_GRAY}Selected: {cy}{asset_sym}{ENDC} @ {tf_str} | Payout≈{ye}{payout}{ENDC}")

                tf_seconds = TIMEFRAMES[tf_str]

                # Historical candles
                candles = await client.get_candles(asset_id, tf_seconds, count=60)
                if candles:
                    df = pd.DataFrame(
                        [
                            {
                                "timestamp": c.timestamp,
                                "open": c.open,
                                "high": c.high,
                                "low": c.low,
                                "close": c.close,
                                "volume": c.volume,
                            }
                            for c in candles
                        ]
                    ).set_index("timestamp")
                    print_candles_table(df.tail(30), asset_sym, tf_str)
                else:
                    rprint(
                        Panel(
                            f"[yellow]No candles received yet for {asset_sym}.[/yellow]",
                            title=f"{info} {PURPLE}Candles{ENDC}",
                            border_style="yellow",
                        )
                    )

                # Subscribe to live 60s candles and print one sample bar
                try:
                    await client.subscribe_symbol(asset_id=asset_id, timeframes=[60])
                    await try_print_one_live_bar(client, asset_id, asset_sym, 60)
                except Exception as e:
                    logger.warning(f"Live stream sample skipped: {e}")

                # Place two small test trades: CALL then PUT
                order = await client.place_order(asset=asset_id, amount=1.0, direction=OrderDirection.CALL, duration=60)
                rprint(f"{info} {DARK_GRAY}Order placed with ID: {ye}{order.order_id}{ENDC}")
                await check_win_task(client, order.order_id)

                order = await client.place_order(asset=asset_id, amount=1.0, direction=OrderDirection.PUT, duration=60)
                rprint(f"{info} {DARK_GRAY}Order placed with ID: {ye}{order.order_id}{ENDC}")
                await check_win_task(client, order.order_id)

                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"{error} Exception in main loop: {e}")
                await asyncio.sleep(5)

    except KeyboardInterrupt:
        logger.info("Stopping due to user interrupt.")
    finally:
        try:
            if client:
                await client.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
