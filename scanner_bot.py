import os
import requests
import time
from datetime import datetime

# ════════════════════════════════════════════════════
#  Налаштування — беруться з змінних середовища
#  (на Railway задаєш у Variables, локально — в .env)
# ════════════════════════════════════════════════════

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

INTERVAL          = "4h"
SCAN_EVERY_SEC    = 4 * 3600
COOLDOWN_SEC      = 4 * 3600
MIN_SIGNALS       = 2

VOLUME_MULTIPLIER = 2.5
RSI_OVERSOLD      = 30
RSI_OVERBOUGHT    = 70
FUNDING_LONG_MAX  = -0.0003
FUNDING_SHORT_MIN = 0.0008
EMA_TOUCH_PCT     = 0.005
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


def get_klines(symbol: str, limit: int = 60) -> list:
    return requests.get(
        f"{BINANCE}/fapi/v1/klines",
        params={"symbol": symbol, "interval": INTERVAL, "limit": limit},
        timeout=10,
    ).json()


def get_funding(symbol: str) -> float:
    data = requests.get(
        f"{BINANCE}/fapi/v1/premiumIndex",
        params={"symbol": symbol},
        timeout=10,
    ).json()
    return float(data["lastFundingRate"])


# ────────── Індикатори ──────────

def ema(prices: list[float], period: int) -> float:
    k = 2 / (period + 1)
    val = sum(prices[:period]) / period
    for p in prices[period:]:
        val = p * k + val * (1 - k)
    return val


def rsi(closes: list[float], period: int = 14) -> float:
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


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    trs = [
        max(highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]))
        for i in range(-period - 1, -1)
    ]
    return sum(trs) / period


def analyze(klines: list) -> dict:
    closes  = [float(k[4]) for k in klines]
    highs   = [float(k[2]) for k in klines]
    lows    = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    price     = closes[-1]
    avg_vol   = sum(volumes[-21:-1]) / 20
    vol_ratio = volumes[-1] / avg_vol if avg_vol else 0
    rsi_val   = rsi(closes)
    ema20     = ema(closes, 20)
    ema50     = ema(closes, 50)
    atr_val   = atr(highs, lows, closes)
    ema_touch = (
        abs(price - ema20) / price < EMA_TOUCH_PCT or
        abs(price - ema50) / price < EMA_TOUCH_PCT
    )

    return {
        "price": price, "vol_ratio": vol_ratio, "rsi": rsi_val,
        "ema20": ema20, "ema50": ema50, "ema_touch": ema_touch, "atr": atr_val,
    }


# ────────── Сигнал ──────────

def check_signals(ind: dict, funding: float) -> dict[str, bool]:
    return {
        "volume":  ind["vol_ratio"] >= VOLUME_MULTIPLIER,
        "rsi":     ind["rsi"] < RSI_OVERSOLD or ind["rsi"] > RSI_OVERBOUGHT,
        "funding": funding > FUNDING_SHORT_MIN or funding < FUNDING_LONG_MAX,
        "ema":     ind["ema_touch"],
    }


def direction(ind: dict, funding: float) -> str | None:
    if ind["rsi"] < RSI_OVERSOLD or funding < FUNDING_LONG_MAX:
        return "ЛОНГ"
    if ind["rsi"] > RSI_OVERBOUGHT or funding > FUNDING_SHORT_MIN:
        return "ШОРТ"
    return None


# ────────── Повідомлення ──────────

def fmt(n: float) -> str:
    if n >= 100: return f"{n:.2f}"
    if n >= 1:   return f"{n:.4f}"
    return f"{n:.6f}"


def build_message(symbol: str, ind: dict, funding: float,
                  hits: dict, side: str | None) -> str:
    price = ind["price"]
    atr_v = ind["atr"]

    if side == "ЛОНГ":
        stop, tp1, tp2 = (price - ATR_STOP_MULT * atr_v,
                          price + ATR_TP1_MULT * atr_v,
                          price + ATR_TP2_MULT * atr_v)
        emoji = "📈"
    elif side == "ШОРТ":
        stop, tp1, tp2 = (price + ATR_STOP_MULT * atr_v,
                          price - ATR_TP1_MULT * atr_v,
                          price - ATR_TP2_MULT * atr_v)
        emoji = "📉"
    else:
        stop, tp1, tp2 = (price - ATR_STOP_MULT * atr_v,
                          price + ATR_TP1_MULT * atr_v,
                          price + ATR_TP2_MULT * atr_v)
        emoji = "⚡"

    def pct(a, b): return (a - b) / b * 100

    v = "✅" if hits["volume"]  else "⬜"
    r = "✅" if hits["rsi"]     else "⬜"
    f = "✅" if hits["funding"] else "⬜"
    e = "✅" if hits["ema"]     else "⬜"

    rsi_label = ("перепроданість" if ind["rsi"] < RSI_OVERSOLD else
                 "перекупленість" if ind["rsi"] > RSI_OVERBOUGHT else "нейтральний")
    ema_label = "близько до EMA20/50" if ind["ema_touch"] else "далеко від EMA"
    side_text = side if side else "невизначений — перевір вручну"

    return (
        f"🔔 <b>СИГНАЛ: {symbol}</b> — {emoji} {side_text}\n\n"
        f"📊 <b>Збіглось {sum(hits.values())}/4 метрик:</b>\n"
        f"{v} Об'єм: {ind['vol_ratio']:.1f}× від середнього\n"
        f"{r} RSI(14): {ind['rsi']:.1f} → {rsi_label}\n"
        f"{f} Funding: {funding * 100:+.4f}%\n"
        f"{e} EMA: {ema_label}\n\n"
        f"💰 Ціна входу:  ${fmt(price)}\n"
        f"🛑 Стоп-лосс:   ${fmt(stop)}  ({pct(stop, price):+.1f}%)\n"
        f"🎯 Тейк 1 (1R): ${fmt(tp1)}  ({pct(tp1, price):+.1f}%) → закрий 50%\n"
        f"🎯 Тейк 2 (2R): ${fmt(tp2)}  ({pct(tp2, price):+.1f}%) → решта\n\n"
        f"📐 ATR(14) = ${fmt(atr_v)}\n"
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
            klines  = get_klines(symbol, limit=60)
            if len(klines) < 55:
                continue
            ind     = analyze(klines)
            funding = get_funding(symbol)
            hits    = check_signals(ind, funding)

            if sum(hits.values()) >= MIN_SIGNALS:
                side = direction(ind, funding)
                send(build_message(symbol, ind, funding, hits, side))
                last_signal[symbol] = now
                found += 1
                print(f"  ✅ {symbol} {sum(hits.values())}/4 | {side} | RSI={ind['rsi']:.0f}", flush=True)

            time.sleep(0.15)

        except Exception as e:
            print(f"  ⚠️  {symbol}: {e}", flush=True)
            continue

    print(f"  Сигналів: {found}", flush=True)


def main() -> None:
    print("🤖 Бот запущено!", flush=True)
    send("🤖 <b>Бот запущено!</b>\nСканую всі USDT-perp монети кожні 4 години.")
    while True:
        scan()
        print("⏳ Наступне сканування через 4h", flush=True)
        time.sleep(SCAN_EVERY_SEC)


if __name__ == "__main__":
    main()
