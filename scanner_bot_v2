import os
import requests
import time
from datetime import datetime

# ════════════════════════════════════════════════════
#  Налаштування
# ════════════════════════════════════════════════════

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

INTERVAL         = "4h"
SCAN_EVERY_SEC   = 4 * 3600
COOLDOWN_SEC     = 4 * 3600
MIN_SIGNALS      = 3          # ← підняли з 2 до 3

# Пороги
VOLUME_MULTIPLIER = 2.5
RSI_OVERSOLD      = 28        # ← трохи жорсткіше ніж 30
RSI_OVERBOUGHT    = 72        # ← трохи жорсткіше ніж 70
BB_PERIOD         = 20
BB_STD            = 2.0
ATR_STOP_MULT     = 1.5
ATR_TP1_MULT      = 1.5
ATR_TP2_MULT      = 3.0

# ════════════════════════════════════════════════════

BINANCE = "https://fapi.binance.com"
last_signal: dict[str, float] = {}


# ────────── Binance API ──────────

def get_all_symbols() -> list[str]:
    data = requests.get(f"{BINANCE}/fapi/v1/exchangeInfo", timeout=10).json()
    return [
        s["symbol"] for s in data["symbols"]
        if s["quoteAsset"] == "USDT"
        and s["status"] == "TRADING"
        and s["contractType"] == "PERPETUAL"
    ]

def get_klines(symbol: str, limit: int = 210) -> list:
    return requests.get(
        f"{BINANCE}/fapi/v1/klines",
        params={"symbol": symbol, "interval": INTERVAL, "limit": limit},
        timeout=10,
    ).json()


# ────────── Індикатори ──────────

def ema_series(prices: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    result = [sum(prices[:period]) / period]
    for p in prices[period:]:
        result.append(p * k + result[-1] * (1 - k))
    return result

def calc_rsi(closes: list[float], period: int = 14) -> float:
    gains, losses = [], []
    for i in range(-period - 1, -1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    if avg_l == 0:
        return 100.0
    return 100 - 100 / (1 + avg_g / avg_l)

def calc_atr(highs, lows, closes, period: int = 14) -> float:
    trs = [
        max(highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]))
        for i in range(-period - 1, -1)
    ]
    return sum(trs) / period

def calc_macd(closes: list[float]):
    """Повертає (macd_prev, signal_prev, macd_curr, signal_curr)."""
    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    # вирівнюємо довжини
    diff = len(ema12) - len(ema26)
    macd_line = [a - b for a, b in zip(ema12[diff:], ema26)]
    signal_line = ema_series(macd_line, 9)
    d = len(macd_line) - len(signal_line)
    macd_aligned = macd_line[d:]
    return (
        macd_aligned[-2], signal_line[-2],   # попередня свічка
        macd_aligned[-1], signal_line[-1],   # поточна свічка
    )

def calc_bb(closes: list[float], period: int = BB_PERIOD, std_mult: float = BB_STD):
    """Повертає (upper, lower, middle) для останньої свічки."""
    window = closes[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std = variance ** 0.5
    return mean + std_mult * std, mean - std_mult * std, mean

def analyze(klines: list) -> dict | None:
    if len(klines) < 205:
        return None

    closes  = [float(k[4]) for k in klines]
    highs   = [float(k[2]) for k in klines]
    lows    = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    price       = closes[-1]
    avg_vol     = sum(volumes[-21:-1]) / 20
    vol_ratio   = volumes[-1] / avg_vol if avg_vol else 0

    rsi_val     = calc_rsi(closes)
    atr_val     = calc_atr(highs, lows, closes)

    # MACD crossover
    mp, sp, mc, sc = calc_macd(closes)
    macd_cross_up   = mp < sp and mc > sc   # бичачий перетин
    macd_cross_down = mp > sp and mc < sc   # ведмежий перетин

    # Bollinger Bands
    bb_upper, bb_lower, bb_mid = calc_bb(closes)
    bb_breakout_up   = price > bb_upper
    bb_breakout_down = price < bb_lower

    # Trend filter — EMA200 (не рахується як сигнал)
    ema200_series = ema_series(closes, 200)
    ema200        = ema200_series[-1]
    trend_up      = price > ema200
    trend_down    = price < ema200

    return {
        "price":            price,
        "vol_ratio":        vol_ratio,
        "rsi":              rsi_val,
        "atr":              atr_val,
        "macd_cross_up":    macd_cross_up,
        "macd_cross_down":  macd_cross_down,
        "bb_upper":         bb_upper,
        "bb_lower":         bb_lower,
        "bb_breakout_up":   bb_breakout_up,
        "bb_breakout_down": bb_breakout_down,
        "ema200":           ema200,
        "trend_up":         trend_up,
        "trend_down":       trend_down,
    }


# ────────── Логіка сигналу ──────────

def check_signals(ind: dict) -> tuple[dict[str, bool], str | None]:
    """
    Повертає (hits, side) або (hits, None) якщо тренд не визначає напрямок.
    Trend filter: якщо немає чіткого тренду — сигнал скасовується.
    """
    # Визначаємо напрямок через trend filter
    if ind["trend_up"]:
        side = "ЛОНГ"
        hits = {
            "volume": ind["vol_ratio"] >= VOLUME_MULTIPLIER,
            "rsi":    ind["rsi"] < RSI_OVERSOLD,
            "macd":   ind["macd_cross_up"],
            "bb":     ind["bb_breakout_down"],   # відскок від нижньої BB в тренді вгору
        }
    elif ind["trend_down"]:
        side = "ШОРТ"
        hits = {
            "volume": ind["vol_ratio"] >= VOLUME_MULTIPLIER,
            "rsi":    ind["rsi"] > RSI_OVERBOUGHT,
            "macd":   ind["macd_cross_down"],
            "bb":     ind["bb_breakout_up"],     # відскок від верхньої BB в тренді вниз
        }
    else:
        return {}, None

    return hits, side


# ────────── Повідомлення ──────────

def fmt(n: float) -> str:
    if n >= 100: return f"{n:.2f}"
    if n >= 1:   return f"{n:.4f}"
    return f"{n:.6f}"

def build_message(symbol: str, ind: dict, hits: dict, side: str) -> str:
    price = ind["price"]
    atr_v = ind["atr"]

    if side == "ЛОНГ":
        stop, tp1, tp2 = (price - ATR_STOP_MULT * atr_v,
                          price + ATR_TP1_MULT * atr_v,
                          price + ATR_TP2_MULT * atr_v)
        emoji = "📈"
    else:
        stop, tp1, tp2 = (price + ATR_STOP_MULT * atr_v,
                          price - ATR_TP1_MULT * atr_v,
                          price - ATR_TP2_MULT * atr_v)
        emoji = "📉"

    def pct(a, b): return (a - b) / b * 100

    v = "✅" if hits["volume"] else "⬜"
    r = "✅" if hits["rsi"]    else "⬜"
    m = "✅" if hits["macd"]   else "⬜"
    b = "✅" if hits["bb"]     else "⬜"

    rsi_label = "перепроданість" if ind["rsi"] < RSI_OVERSOLD else "перекупленість"
    bb_label  = ("нижня BB пробита" if ind["bb_breakout_down"]
                 else "верхня BB пробита" if ind["bb_breakout_up"]
                 else "в межах BB")
    trend_label = f"EMA200 = ${fmt(ind['ema200'])}"
    count = sum(hits.values())

    return (
        f"🔔 <b>СИГНАЛ: {symbol}</b> — {emoji} {side}\n\n"
        f"📊 <b>Збіглось {count}/4 метрик:</b>\n"
        f"{v} Об'єм: {ind['vol_ratio']:.1f}× від середнього\n"
        f"{r} RSI(14): {ind['rsi']:.1f} → {rsi_label}\n"
        f"{m} MACD: {'перетин ↑' if hits['macd'] and side == 'ЛОНГ' else 'перетин ↓' if hits['macd'] else 'без перетину'}\n"
        f"{b} BB: {bb_label}\n\n"
        f"📐 Тренд: ціна {'вище' if side == 'ЛОНГ' else 'нижче'} {trend_label}\n\n"
        f"💰 Ціна входу:  ${fmt(price)}\n"
        f"🛑 Стоп-лосс:   ${fmt(stop)}  ({pct(stop, price):+.1f}%)\n"
        f"🎯 Тейк 1 (1R): ${fmt(tp1)}  ({pct(tp1, price):+.1f}%) → закрий 50%\n"
        f"🎯 Тейк 2 (2R): ${fmt(tp2)}  ({pct(tp2, price):+.1f}%) → решта\n\n"
        f"⏰ {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC\n\n"
        f"⚠️ <i>Перевір графік перед входом</i>"
    )


# ────────── Telegram ──────────

def send(text: str) -> None:
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )


# ────────── Головний цикл ──────────

def scan() -> None:
    now = time.time()
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] Сканування...", flush=True)

    try:
        symbols = get_all_symbols()
    except Exception as e:
        print(f"  ❌ Список монет: {e}", flush=True)
        return

    print(f"  Монет: {len(symbols)}", flush=True)
    found = 0

    for symbol in symbols:
        if now - last_signal.get(symbol, 0) < COOLDOWN_SEC:
            continue
        try:
            klines = get_klines(symbol, limit=210)
            ind    = analyze(klines)
            if ind is None:
                continue

            hits, side = check_signals(ind)
            if side and sum(hits.values()) >= MIN_SIGNALS:
                send(build_message(symbol, ind, hits, side))
                last_signal[symbol] = now
                found += 1
                print(f"  ✅ {symbol} {sum(hits.values())}/4 | {side} | RSI={ind['rsi']:.0f} | Vol={ind['vol_ratio']:.1f}×", flush=True)

            time.sleep(0.15)

        except Exception as e:
            print(f"  ⚠️  {symbol}: {e}", flush=True)
            continue

    print(f"  Сигналів: {found}", flush=True)


def main() -> None:
    print("🤖 Бот v2 запущено!", flush=True)
    send(
        "🤖 <b>Бот v2 запущено!</b>\n\n"
        "Оновлення:\n"
        "✅ MACD crossover замість EMA touch\n"
        "✅ Bollinger Bands замість Funding rate\n"
        "✅ Trend filter (EMA200)\n"
        "✅ Поріг підвищено до 3/4\n\n"
        "Сканую кожні 4 години."
    )
    while True:
        scan()
        print("⏳ Наступне сканування через 4h", flush=True)
        time.sleep(SCAN_EVERY_SEC)


if __name__ == "__main__":
    main()
