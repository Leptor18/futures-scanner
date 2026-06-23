# Binance Futures Scanner Bot

Telegram-бот що сканує всі USDT-perp ф'ючерси на Binance
і надсилає сигнали з точками входу, стопом і тейком.

## Змінні середовища (обов'язкові)

| Змінна | Де взяти |
|--------|----------|
| `TELEGRAM_TOKEN` | @BotFather в Telegram |
| `TELEGRAM_CHAT_ID` | @userinfobot в Telegram |

## Локальний запуск

```bash
pip install -r requirements.txt
TELEGRAM_TOKEN=xxx TELEGRAM_CHAT_ID=yyy python scanner_bot.py
```

## Деплой на Railway

1. Залий цю папку на GitHub
2. railway.app → New Project → Deploy from GitHub
3. Variables → додай TELEGRAM_TOKEN і TELEGRAM_CHAT_ID
4. Deploy → бот запрацює автоматично
