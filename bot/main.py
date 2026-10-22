import asyncio
import os

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from backend.app.config import settings
from backend.app.database import Base, SessionLocal, engine
from backend.app.models import ColonizationRequest, User
from backend.app.services import bind_telegram, seed_database, state_for_user


router = Router()


def ensure_db() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)


@router.message(Command("start"))
async def start(message: Message) -> None:
    await message.answer("Polis Map bot. Используйте /link <code>, /profile, /map или /actions.")


@router.message(Command("link"))
async def link(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer("Формат: /link ABC123")
        return
    try:
        with SessionLocal() as db:
            user = bind_telegram(
                db,
                command.args.strip().upper(),
                str(message.from_user.id),
                message.from_user.username if message.from_user else None,
            )
            state = state_for_user(db, user)
        suffix = f"\nГосударство: {state.name}" if state else ""
        await message.answer(f"Аккаунт успешно привязан.\nИгрок: {user.username}{suffix}")
    except ValueError as error:
        await message.answer(str(error))


@router.message(Command("profile"))
async def profile(message: Message) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == str(message.from_user.id)))
    if not user:
        await message.answer("Telegram не привязан. Получите код в web UI и отправьте /link <code>.")
        return
    await message.answer(f"Игрок: {user.username}\nРоль: {user.role}")


@router.message(Command("map"))
async def map_link(message: Message) -> None:
    await message.answer(f"Карта: {settings.frontend_url}")


@router.message(Command("actions"))
async def actions(message: Message) -> None:
    with SessionLocal() as db:
        rows = db.scalars(select(ColonizationRequest).order_by(ColonizationRequest.id.desc()).limit(5)).all()
    if not rows:
        await message.answer("Активных заявок пока нет.")
        return
    text = "\n".join(f"#{row.id}: state {row.state_id} -> territory {row.territory_id}, {row.status}" for row in rows)
    await message.answer(text)


async def main() -> None:
    token = settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("TELEGRAM_BOT_TOKEN is empty; bot is disabled.")
        return
    ensure_db()
    bot = Bot(token)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
