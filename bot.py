import asyncio
import contextlib
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, Update,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from config import BOT_TOKEN, CHANNEL, CHANNEL_URL, ADMIN_ID, FILES
from texts import WELCOME, NO_SUB, ABOUT, CONTACT, PROJECTS
import db

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())


class Broadcast(StatesGroup):
    waiting_text = State()


# ---------- helpers ----------

def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=c) for t, c in row]
        for row in rows
    ])


async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL, user_id)
        return member.status not in ("left", "kicked")
    except TelegramAPIError as e:
        # Чаще всего: бот не админ в канале или неверный @username в config.py
        print(f"[sub-check] Ошибка проверки подписки: {e}")
        return False


def subscribe_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")],
    ])


def main_menu() -> InlineKeyboardMarkup:
    return kb([
        [("👤 Обо мне", "about")],
        [("🚀 Проекты", "projects")],
        [("💬 Связаться / фидбек", "contact")],
    ])


async def require_sub(cb: CallbackQuery) -> bool:
    """True = подписан, можно продолжать."""
    if await is_subscribed(cb.from_user.id):
        return True
    await cb.message.edit_text(NO_SUB, reply_markup=subscribe_kb())
    await cb.answer()
    return False


# ---------- /start ----------

@dp.message(CommandStart())
async def start(message: Message):
    await db.add_user(message.from_user.id)
    if await is_subscribed(message.from_user.id):
        await message.answer(WELCOME, reply_markup=main_menu())
    else:
        await message.answer(WELCOME)
        await message.answer(NO_SUB, reply_markup=subscribe_kb())


@dp.callback_query(F.data == "check_sub")
async def check_sub(cb: CallbackQuery):
    await db.add_user(cb.from_user.id)
    if await is_subscribed(cb.from_user.id):
        await cb.message.edit_text("✅ Подписка подтверждена!", reply_markup=main_menu())
    else:
        await cb.answer(
            "Не вижу подписку. Если ты точно подписан - "
            "проверь, что бот добавлен в админы канала.",
            show_alert=True,
        )
    await cb.answer()


# ---------- ловим файлы от админа, чтобы получить file_id ----------

@dp.message(F.document)
async def catch_file(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            f"📎 file_id этого файла:\n<code>{message.document.file_id}</code>\n\n"
            "Вставь его в config.py → FILES"
        )


# ---------- главное меню ----------

@dp.callback_query(F.data == "main")
async def to_main(cb: CallbackQuery):
    if not await require_sub(cb):
        return
    await cb.message.edit_text("Главное меню:", reply_markup=main_menu())
    await cb.answer()


@dp.callback_query(F.data == "about")
async def about(cb: CallbackQuery):
    if not await require_sub(cb):
        return
    await cb.message.edit_text(ABOUT, reply_markup=kb([[("⬅️ Назад", "main")]]))
    await cb.answer()


@dp.callback_query(F.data == "contact")
async def contact(cb: CallbackQuery):
    if not await require_sub(cb):
        return
    await cb.message.edit_text(CONTACT, reply_markup=kb([[("⬅️ Назад", "main")]]))
    await cb.answer()


# ---------- проекты ----------

@dp.callback_query(F.data == "projects")
async def projects(cb: CallbackQuery):
    if not await require_sub(cb):
        return
    rows = [[(p["name"], f"project:{key}")] for key, p in PROJECTS.items()]
    rows.append([("⬅️ Назад", "main")])
    await cb.message.edit_text("🚀 Мои проекты:", reply_markup=kb(rows))
    await cb.answer()


@dp.callback_query(F.data.startswith("project:"))
async def project(cb: CallbackQuery):
    if not await require_sub(cb):
        return
    key = cb.data.split(":", 1)[1]
    p = PROJECTS[key]
    await cb.message.edit_text(
        p["description"],
        reply_markup=kb([
            [("📥 Скачать", f"dl:{key}")],
            [("📖 Как пользоваться", f"guide:{key}")],
            [("✨ Фишки", f"tips:{key}")],
            [("❓ FAQ", f"faq:{key}")],
            [("📜 Обновления", f"changelog:{key}")],
            [("⬅️ К проектам", "projects")],
        ]),
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("dl:"))
async def download(cb: CallbackQuery):
    if not await require_sub(cb):
        return
    key = cb.data.split(":", 1)[1]
    p = PROJECTS[key]
    file_id = FILES.get(key, "")
    if not file_id or file_id.startswith("ВСТАВЬ"):
        await cb.answer("Файл скоро появится", show_alert=True)
        return
    await cb.message.answer_document(file_id, caption=f"📥 {p['name']}")
    await cb.answer()


@dp.callback_query(F.data.startswith(("guide:", "tips:", "changelog:")))
async def info_section(cb: CallbackQuery):
    if not await require_sub(cb):
        return
    section, key = cb.data.split(":", 1)
    p = PROJECTS[key]
    await cb.message.edit_text(
        p[section],
        reply_markup=kb([[("⬅️ Назад", f"project:{key}")]]),
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("faq:"))
async def faq(cb: CallbackQuery):
    if not await require_sub(cb):
        return
    key = cb.data.split(":", 1)[1]
    p = PROJECTS[key]
    rows = [[(q, f"faqa:{key}:{i}")] for i, q in enumerate(p["faq"])]
    rows.append([("⬅️ Назад", f"project:{key}")])
    await cb.message.edit_text(f"❓ FAQ - {p['name']}:", reply_markup=kb(rows))
    await cb.answer()


@dp.callback_query(F.data.startswith("faqa:"))
async def faq_answer(cb: CallbackQuery):
    if not await require_sub(cb):
        return
    _, key, idx = cb.data.split(":")
    p = PROJECTS[key]
    question, answer = list(p["faq"].items())[int(idx)]
    await cb.message.edit_text(
        f"<b>{question}</b>\n\n{answer}",
        reply_markup=kb([[("⬅️ К FAQ", f"faq:{key}")]]),
    )
    await cb.answer()


# ---------- админ-панель ----------

@dp.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = await db.get_all_users()
    await message.answer(
        f"🛠 <b>Админ-панель</b>\n\nПользователей в базе: {len(users)}",
        reply_markup=kb([[("📣 Уведомить пользователей", "broadcast")]]),
    )


@dp.callback_query(F.data == "broadcast")
async def broadcast_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        return
    await state.set_state(Broadcast.waiting_text)
    await cb.message.answer(
        "📣 Напиши текст уведомления следующим сообщением.\n"
        "Оно уйдёт всем пользователям бота.\n\n/cancel - отмена"
    )
    await cb.answer()


@dp.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")


@dp.message(Broadcast.waiting_text)
async def broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    users = await db.get_all_users()
    sent, failed = 0, 0
    status = await message.answer(f"⏳ Рассылка: 0/{len(users)}")
    for user_id in users:
        try:
            await bot.send_message(user_id, message.text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # лимит Telegram ~30 msg/сек
        if sent % 25 == 0:
            with contextlib.suppress(Exception):
                await status.edit_text(f"⏳ Рассылка: {sent}/{len(users)}")
    await status.edit_text(
        f"✅ Рассылка завершена.\nДоставлено: {sent}\nНе доставлено: {failed}"
    )


# ---------- запуск ----------

async def webhook_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        update = Update.model_validate(data)
        await dp.feed_webhook_update(bot, update)
        return web.Response(text="ok")
    except Exception as e:
        print(f"[webhook] Ошибка обработки обновления: {e}")
        return web.Response(status=500, text="error")


async def main():
    await db.init_db()

    # Render Web Service предоставляет внешний HTTPS-адрес и порт.
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    port = int(os.getenv("PORT", "10000"))
    if not render_url:
        raise RuntimeError(
            "Не задана переменная RENDER_EXTERNAL_URL. "
            "Запусти бота на Render Web Service или задай URL вручную."
        )

    webhook_path = "/telegram-webhook"
    await bot.set_webhook(render_url + webhook_path, drop_pending_updates=True)

    app = web.Application()
    app.router.add_post(webhook_path, webhook_handler)
    app.router.add_get("/", lambda request: web.Response(text="Bot is running"))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Webhook запущен: {render_url}{webhook_path}")

    try:
        await asyncio.Event().wait()
    finally:
        await bot.delete_webhook()
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
