"""
Бот пересылает сообщения с хэштегом #отчетыОлим из всех бесед,
где он состоит, в одну общую группу.

Установка:  pip install aiogram
Запуск:     BOT_TOKEN=... TARGET_CHAT_ID=-100... python bot.py
"""
import asyncio
import html
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import Message

BOT_TOKEN = os.environ["BOT_TOKEN"]
TARGET_CHAT_ID = int(os.environ.get("TARGET_CHAT_ID", "0"))
HASHTAG = "#отчетыолим"  # сравнение без учёта регистра

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()


def has_hashtag(message: Message) -> bool:
    text = (message.text or message.caption or "").lower().replace("ё", "е")
    return HASHTAG in text


@dp.message(Command("id"))
async def cmd_id(message: Message):
    """Отправьте /id в общей группе, чтобы узнать её TARGET_CHAT_ID."""
    await message.reply(f"ID этого чата: <code>{message.chat.id}</code>", parse_mode="HTML")


async def deliver(bot: Bot, messages: list[Message]):
    """Отправляет в общую группу заголовок и все сообщения отчёта."""
    first = messages[0]
    author = first.from_user.full_name if first.from_user else "неизвестно"
    header = (
        f"📌 <b>{html.escape(first.chat.title or 'Беседа')}</b> — "
        f"{html.escape(author)}"
    )
    await bot.send_message(TARGET_CHAT_ID, header, parse_mode="HTML")
    ids = sorted(m.message_id for m in messages)
    try:
        await bot.forward_messages(TARGET_CHAT_ID, first.chat.id, ids)
    except (TelegramBadRequest, TelegramForbiddenError):
        # например, в исходной беседе запрещена пересылка — копируем содержимое
        await bot.copy_messages(TARGET_CHAT_ID, first.chat.id, ids)


GROUP_FILTERS = (F.chat.type.in_({"group", "supergroup"}), F.chat.id != TARGET_CHAT_ID)

# Альбом (несколько фото/файлов в одном сообщении) приходит как отдельные
# сообщения с общим media_group_id, а подпись есть только у одного из них.
album_buffer: dict[str, list[Message]] = {}
ALBUM_WAIT_SECONDS = 1.5


@dp.message(*GROUP_FILTERS, F.media_group_id)
async def collect_album(message: Message, bot: Bot):
    group_id = message.media_group_id
    if group_id in album_buffer:
        album_buffer[group_id].append(message)
        return
    album_buffer[group_id] = [message]
    await asyncio.sleep(ALBUM_WAIT_SECONDS)  # ждём остальные части альбома
    messages = album_buffer.pop(group_id)
    if any(has_hashtag(m) for m in messages):
        await deliver(bot, messages)


@dp.message(*GROUP_FILTERS, ~F.media_group_id, has_hashtag)
async def collect(message: Message, bot: Bot):
    await deliver(bot, [message])


from aiohttp import web

async def handle_ping(request):
    return web.Response(text="Bot is alive!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render автоматически задает переменную PORT, которую мы должны слушать
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    bot = Bot(BOT_TOKEN)
    # 1. Запускаем фейковый веб-сервер, чтобы Render был доволен
    await web_server()
    # 2. Запускаем самого бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
