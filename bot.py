import os
import vk_api
import requests

from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id
from dotenv import load_dotenv

load_dotenv()

VK_TOKEN = os.getenv("VK_TOKEN")
API_URL = os.getenv("API_URL", "http://127.0.0.1:8001")
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "super-secret-key-change-me")

GROUP_ID = 243085760

if not VK_TOKEN:
    raise RuntimeError("VK_TOKEN не найден в .env")

vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

print("VK-бот запущен!")

# Состояния пользователей: {vk_id: "awaiting_expense"}
user_states = {}


# ============================================================
# УТИЛИТЫ
# ============================================================
def api_post(path, data):
    try:
        return requests.post(
            f"{API_URL}{path}",
            json=data,
            headers={"x-api-key": API_SECRET_KEY},
            timeout=5
        )
    except requests.RequestException as e:
        print(f"API error: {e}")
        return None


def send(vk_user_id, text, keyboard=None):
    try:
        params = {
            "user_id": vk_user_id,
            "message": text,
            "random_id": get_random_id(),
        }
        if keyboard is not None:
            params["keyboard"] = keyboard.get_keyboard()
        vk.messages.send(**params)
    except Exception as e:
        print(f"Send error: {e}")


def make_main_keyboard():
    kb = VkKeyboard(one_time=False, inline=False)
    kb.add_button("💰 Баланс", color=VkKeyboardColor.PRIMARY)
    kb.add_button("➕ Добавить трату", color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button("🔗 Привязать ВК", color=VkKeyboardColor.SECONDARY)
    kb.add_button("ℹ️ Помощь", color=VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button("🧹 Очистить чат", color=VkKeyboardColor.NEGATIVE)
    return kb


def make_cancel_inline():
    """Inline-кнопка отмены, привязанная к сообщению."""
    kb = VkKeyboard(inline=True)
    kb.add_button("⬅️ Отмена", color=VkKeyboardColor.SECONDARY)
    return kb


def delete_history(vk_user_id, count=50):
    try:
        history = vk.messages.getHistory(user_id=vk_user_id, count=count, rev=0)
        items = history.get("items", [])
        message_ids = [str(m["id"]) for m in items if m.get("out") == 1]
        if not message_ids:
            return 0
        vk.messages.delete(message_ids=",".join(message_ids), delete_for_all=1)
        return len(message_ids)
    except Exception as e:
        print(f"Delete error: {e}")
        return -1


# ============================================================
# ОБРАБОТКА
# ============================================================
for event in longpoll.listen():
    if event.type != VkBotEventType.MESSAGE_NEW:
        continue

    vk_id = event.object.message["from_id"]
    text = event.object.message.get("text", "").strip()
    print(f"[{vk_id}] {text}")

    if not text:
        continue

    low = text.lower()
    state = user_states.get(vk_id)

    # ---------- Отмена в любом состоянии ----------
    if low in ("⬅️ отмена", "/cancel", "отмена"):
        user_states.pop(vk_id, None)
        send(vk_id, "Ок, отменил.", keyboard=make_main_keyboard())
        continue

    # ---------- Если ждём ввод траты ----------
    if state == "awaiting_expense":
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            send(vk_id, "❌ Формат: СУММА КАТЕГОРИЯ\nНапример: 500 еда", keyboard=make_cancel_inline())
            continue
        try:
            amount = float(parts[0].replace(",", "."))
        except ValueError:
            send(vk_id, "❌ Сумма должна быть числом. Попробуй: 500 еда", keyboard=make_cancel_inline())
            continue
        category = parts[1].strip()
        resp = api_post("/api/add/", {
            "vk_id": vk_id,
            "amount": amount,
            "category": category,
            "type": "expense"
        })
        user_states.pop(vk_id, None)
        if resp is None:
            send(vk_id, "⚠️ Сервер недоступен.", keyboard=make_main_keyboard())
        elif resp.status_code == 200:
            send(vk_id, f"✅ {amount:.2f} ₽ «{category}» добавлено.", keyboard=make_main_keyboard())
        else:
            send(vk_id, "❌ Сначала привяжи аккаунт: /link КОД", keyboard=make_main_keyboard())
        continue

    # ---------- /start и /help ----------
    if low in ("/start", "/help", "помощь", "начать", "ℹ️ помощь"):
        send(
            vk_id,
            "👋 Привет! Я бот для учёта бюджета.\n\n"
            "Выбери действие на клавиатуре ниже 👇",
            keyboard=make_main_keyboard()
        )
        continue

    # ---------- Баланс ----------
    if low in ("💰 баланс", "/balance", "баланс"):
        resp = api_post("/api/balance/", {"vk_id": vk_id})
        if resp is None:
            send(vk_id, "⚠️ Сервер недоступен.", keyboard=make_main_keyboard())
        elif resp.status_code == 200:
            d = resp.json()
            send(
                vk_id,
                f"💰 Баланс: {d['balance']:.2f} ₽\n"
                f"📈 Доходы: {d['income']:.2f} ₽\n"
                f"📉 Расходы: {d['expenses']:.2f} ₽",
                keyboard=make_main_keyboard()
            )
        else:
            send(vk_id, "🔗 Сначала привяжи аккаунт.", keyboard=make_main_keyboard())
        continue

    # ---------- Привязка ----------
    if low in ("🔗 привязать вк", "/link", "привязать"):
        send(
            vk_id,
            "🔗 Зайди на сайт → Профиль → Привязать ВК → получи код.\n"
            "Потом отправь сюда: /link ТВОЙ_КОД",
            keyboard=make_main_keyboard()
        )
        continue

    if low.startswith("/link "):
        code = text[6:].strip()
        resp = api_post("/api/link/", {"vk_id": vk_id, "code": code})
        if resp is None:
            send(vk_id, "⚠️ Сервер недоступен.", keyboard=make_main_keyboard())
        elif resp.status_code == 200:
            send(vk_id, "✅ Аккаунт привязан!", keyboard=make_main_keyboard())
        else:
            try:
                err = resp.json().get('error', 'Ошибка')
            except Exception:
                err = 'Ошибка'
            send(vk_id, f"❌ {err}", keyboard=make_main_keyboard())
        continue

    # ---------- Добавить трату ----------
    if low in ("➕ добавить трату", "/add", "добавить"):
        user_states[vk_id] = "awaiting_expense"
        send(
            vk_id,
            "➕ Напиши трату в формате:\n\n"
            "   СУММА КАТЕГОРИЯ\n\n"
            "Например: 500 еда",
            keyboard=make_cancel_inline()
        )
        continue

    # ---------- Очистить чат ----------
    if low in ("🧹 очистить чат", "/clear", "очистить"):
        send(vk_id, "🧹 Удаляю сообщения...", keyboard=make_main_keyboard())
        deleted = delete_history(vk_id, count=50)
        if deleted > 0:
            send(vk_id, f"✅ Удалено: {deleted}", keyboard=make_main_keyboard())
        elif deleted == 0:
            send(vk_id, "🤷 Нечего удалять.", keyboard=make_main_keyboard())
        else:
            send(vk_id, "⚠️ Не удалось удалить.", keyboard=make_main_keyboard())
        continue

    # ---------- Неизвестная команда ----------
    send(vk_id, "❓ Не понял. Используй кнопки ниже 👇", keyboard=make_main_keyboard())