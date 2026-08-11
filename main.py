import asyncio
import logging
import sqlite3
import os
from typing import Callable, Dict, Any, Awaitable

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, TelegramObject, FSInputFile
)
from aiogram.enums import ChatMemberStatus
import openpyxl

# Logging
logging.basicConfig(level=logging.INFO)

# Configuration
BOT_TOKEN = "8910678581:AAFCgInJ04YEBc4lPBuNA8eJRIkK2dbzCDw"  # Bot tokeningizni kiriting
ADMIN_CODE = "dev1422"
CHANNEL_ID = "@registan_abituriyent"  # Kanal username yoki ID
CHANNEL_LINK = "https://t.me/registan_abituriyent"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==================== DATABASE SETUP ====================
DB_NAME = "voting_bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Foydalanuvchilar (Statistika, Mailing va Excel uchun)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        full_name TEXT,
        username TEXT,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # Fan va tillar
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )""")
    
    # Ustozlar
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )""")
    
    # Dars kunlari
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS days (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )""")
    
    # Guruhlar
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER,
        teacher_id INTEGER,
        day_id INTEGER,
        time_text TEXT,
        photo_id TEXT,
        votes INTEGER DEFAULT 0,
        FOREIGN KEY(subject_id) REFERENCES subjects(id),
        FOREIGN KEY(teacher_id) REFERENCES teachers(id),
        FOREIGN KEY(day_id) REFERENCES days(id)
    )""")
    
    # Ovozlar
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS votes (
        user_id INTEGER PRIMARY KEY,
        group_id INTEGER
    )""")

    # Boshlang'ich standart ma'lumotlar
    cursor.executemany("INSERT OR IGNORE INTO subjects (name) VALUES (?)", [("Matematika",), ("Informatika",), ("Ingliz tili",)])
    cursor.executemany("INSERT OR IGNORE INTO teachers (name) VALUES (?)", [("Ali Valiyev",), ("Eshmat Toshmatov",)])
    cursor.executemany("INSERT OR IGNORE INTO days (name) VALUES (?)", [("Juft kunlar (Se-Pay-Shan)",), ("Toq kunlar (Du-Chor-Jum)",)])
    
    conn.commit()
    conn.close()

init_db()

# ==================== STATES ====================
class AdminStates(StatesGroup):
    waiting_code = State()
    in_admin = State()
    # Add Group
    add_group_subject = State()
    add_group_teacher = State()
    add_group_day = State()
    add_group_time = State()
    add_group_photo = State()
    # Settings Management
    manage_items = State()
    # Mailing
    waiting_broadcast_message = State()

class UserStates(StatesGroup):
    choosing_subject = State()
    choosing_teacher = State()
    choosing_group = State()
    confirm_vote = State()

# ==================== MIDDLEWARE (MAJBURIY OBUNA) ====================
class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
            text = event.text or ""
            if text.startswith("/dev"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            if event.data == "check_sub":
                return await handler(event, data)

        if user_id:
            try:
                member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
                if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                    kbd = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Obuna bo'lish", url=CHANNEL_LINK)],
                        [InlineKeyboardButton(text="Tekshirish", callback_data="check_sub")]
                    ])
                    msg_text = "Iltimos, ovoz berish uchun avval telegram kanalimizga obuna bo'ling"
                    if isinstance(event, Message):
                        await event.answer(msg_text, reply_markup=kbd)
                    elif isinstance(event, CallbackQuery):
                        await event.message.answer(msg_text, reply_markup=kbd)
                        await event.answer()
                    return
            except Exception:
                pass

        return await handler(event, data)

dp.message.outer_middleware(SubscriptionMiddleware())
dp.callback_query.outer_middleware(SubscriptionMiddleware())

# ==================== KEYBOARDS ====================
def main_user_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🗳 Ovoz berish")]],
        resize_keyboard=True
    )

def admin_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Guruhlar statistikasi"), KeyboardButton(text="📈 Bot statistikasi")],
            [KeyboardButton(text="➕ Guruh qo'shish"), KeyboardButton(text="📂 Mavjud guruhlar")],
            [KeyboardButton(text="📢 Xabar yuborish"), KeyboardButton(text="📥 Excel yuklab olish")],
            [KeyboardButton(text="⚙️ Settings")]
        ],
        resize_keyboard=True
    )

def settings_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👨‍🏫 Ustozlar"), KeyboardButton(text="📚 Fan va tillar")],
            [KeyboardButton(text="📅 Dars kunlari"), KeyboardButton(text="⬅️ Bosh menyu")]
        ],
        resize_keyboard=True
    )

def cancel_reply_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

# ==================== GLOBAL MENU NAVIGATION (STATE OVERRIDE) ====================
@dp.message(F.text == "⬅️ Bosh menyu")
async def global_back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.in_admin)
    await message.answer("Bosh menyu:", reply_markup=admin_main_kb())

@dp.message(F.text == "⚙️ Settings")
async def global_settings(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.in_admin)
    await message.answer("Settings bo'limi:", reply_markup=settings_kb())

@dp.message(F.text == "📊 Guruhlar statistikasi")
async def global_stats(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.in_admin)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.name, t.name, d.name, g.time_text, g.votes 
        FROM groups g
        JOIN subjects s ON g.subject_id = s.id
        JOIN teachers t ON g.teacher_id = t.id
        JOIN days d ON g.day_id = d.id
        ORDER BY g.votes DESC
    """)
    groups = cursor.fetchall()
    conn.close()

    if not groups:
        return await message.answer("Hozircha hech qanday guruh yaratilmagan.", reply_markup=admin_main_kb())

    text = "📊 **Guruhlar statistikasi va ovozlar:**\n\n"
    for idx, g in enumerate(groups, 1):
        text += f"{idx}. {g[0]} | {g[1]} | {g[2]} ({g[3]}) — **{g[4]} ta ovoz**\n"

    await message.answer(text, reply_markup=admin_main_kb())

@dp.message(F.text == "📈 Bot statistikasi")
async def global_bot_stats(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.in_admin)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM votes")
    voted_count = cursor.fetchone()[0]
    conn.close()

    await message.answer(
        f"📈 **Bot statistikasi:**\n\n"
        f"👤 Botdan ro'yxatdan o'tganlar (Start bosganlar): **{user_count} ta**\n"
        f"🗳 Ovoz berganlar: **{voted_count} ta**",
        reply_markup=admin_main_kb()
    )

@dp.message(F.text == "📂 Mavjud guruhlar")
async def global_list_groups(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.in_admin)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT g.id, s.name, t.name, d.name, g.time_text 
        FROM groups g
        JOIN subjects s ON g.subject_id = s.id
        JOIN teachers t ON g.teacher_id = t.id
        JOIN days d ON g.day_id = d.id
    """)
    groups = cursor.fetchall()
    conn.close()

    if not groups:
        return await message.answer("Guruhlar mavjud emas.", reply_markup=admin_main_kb())

    for g in groups:
        txt = f"🆔 {g[0]} | {g[1]} | Ustoz: {g[2]} | {g[3]} ({g[4]})"
        kbd = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_group_{g[0]}")]
        ])
        await message.answer(txt, reply_markup=kbd)

@dp.message(F.text == "❌ Bekor qilish")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.in_admin)
    await message.answer("Jarayon bekor qilindi.", reply_markup=admin_main_kb())

# ==================== EXCEL DOWNLOAD ====================
@dp.message(F.text == "📥 Excel yuklab olish")
async def export_users_excel(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.in_admin)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, full_name, username, joined_at FROM users")
    users = cursor.fetchall()
    conn.close()

    if not users:
        return await message.answer("Foydalanuvchilar topilmadi.")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Foydalanuvchilar"
    
    # Header
    ws.append(["User ID", "Ism-Familiya", "Username", "Ro'yxatdan o'tgan sana"])

    for user in users:
        ws.append([user[0], user[1], f"@{user[2]}" if user[2] else "Mavjud emas", user[3]])

    file_path = "bot_users.xlsx"
    wb.save(file_path)

    excel_file = FSInputFile(file_path)
    await message.answer_document(excel_file, caption="📊 Bot foydalanuvchilari ro'yxati")
    
    if os.path.exists(file_path):
        os.remove(file_path)

# ==================== BROADCAST / MAILING ====================
@dp.message(F.text == "📢 Xabar yuborish")
async def start_broadcast(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Foydalanuvchilarga yubormoqchi bo'lgan xabaringizni kiriting (Text, Rasm, Video, Ovozli xabar va h.k.):",
        reply_markup=cancel_reply_kb()
    )
    await state.set_state(AdminStates.waiting_broadcast_message)

@dp.message(AdminStates.waiting_broadcast_message)
async def process_broadcast(message: Message, state: FSMContext):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    if not users:
        await message.answer("Foydalanuvchilar topilmadi.", reply_markup=admin_main_kb())
        await state.set_state(AdminStates.in_admin)
        return

    status_msg = await message.answer(f"Xabar yuborish boshlandi. Jami foydalanuvchilar: {len(users)} ta...")

    success_count = 0
    fail_count = 0

    for u in users:
        u_id = u[0]
        try:
            await message.copy_to(chat_id=u_id)
            success_count += 1
            await asyncio.sleep(0.05) # Rate limit saqlash uchun
        except Exception:
            fail_count += 1

    await status_msg.edit_text(
        f"✅ **Xabar yuborish yakunlandi!**\n\n"
        f"🟢 Muvaffaqiyatli yetkazildi: **{success_count} ta**\n"
        f"🔴 Etkazilmadi (bloklaganlar): **{fail_count} ta**"
    )
    await message.answer("Bosh menyu:", reply_markup=admin_main_kb())
    await state.set_state(AdminStates.in_admin)

# ==================== USER HANDLERS ====================
@dp.message(CommandStart())
async def user_start(message: Message, state: FSMContext):
    await state.clear()
    
    # Save User to DB
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, full_name, username)
        VALUES (?, ?, ?)
    """, (message.from_user.id, message.from_user.full_name, message.from_user.username))
    conn.commit()
    conn.close()

    await message.answer(
        f"Assalomu alaykum {message.from_user.full_name}, Registon o'quv markazining 'Guruhlar Tanlovi'ga xush kelibsiz.\n\n"
        "Quyidagi tugmalar orqali guruh tanlang va unga ovoz bering.",
        reply_markup=main_user_kb()
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_handler(call: CallbackQuery):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=call.from_user.id)
        if member.status not in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
            await call.message.delete()
            await call.message.answer("Obuna tasdiqlandi! Endi botdan foydalanishingiz mumkin.", reply_markup=main_user_kb())
        else:
            await call.answer("Siz hali kanalga obuna bo'lmadingiz", show_alert=True)
    except Exception:
        await call.answer("Xatolik yuz berdi. Kanalni tekshiring.", show_alert=True)

@dp.message(F.text == "🗳 Ovoz berish")
async def start_voting(message: Message, state: FSMContext):
    await state.clear()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM votes WHERE user_id = ?", (message.from_user.id,))
    if cursor.fetchone():
        conn.close()
        return await message.answer("Siz allaqachon ovoz bergansiz! Bir foydalanuvchi faqat 1 marta ovoz berishi mumkin.")

    cursor.execute("SELECT * FROM subjects")
    subjects = cursor.fetchall()
    conn.close()

    if not subjects:
        return await message.answer("Hozircha fanlar mavjud emas.")

    kbd = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=sub[1], callback_data=f"user_sub_{sub[0]}")] for sub in subjects
    ])
    await message.answer("Fan/tilni tanlang:", reply_markup=kbd)
    await state.set_state(UserStates.choosing_subject)

@dp.callback_query(F.data.startswith("user_sub_"), UserStates.choosing_subject)
async def user_choose_teacher(call: CallbackQuery, state: FSMContext):
    sub_id = int(call.data.split("_")[2])
    await state.update_data(sub_id=sub_id)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT t.id, t.name FROM teachers t
        JOIN groups g ON g.teacher_id = t.id
        WHERE g.subject_id = ?
    """, (sub_id,))
    teachers = cursor.fetchall()
    conn.close()

    if not teachers:
        return await call.message.edit_text("Ushbu fan bo'yicha guruhlar mavjud emas.")

    kbd = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t[1], callback_data=f"user_teach_{t[0]}")] for t in teachers
    ])
    await call.message.edit_text("Ustozni tanlang:", reply_markup=kbd)
    await state.set_state(UserStates.choosing_teacher)

@dp.callback_query(F.data.startswith("user_teach_"), UserStates.choosing_teacher)
async def user_show_groups(call: CallbackQuery, state: FSMContext):
    teach_id = int(call.data.split("_")[2])
    data = await state.get_data()
    sub_id = data['sub_id']

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT g.id, s.name, t.name, d.name, g.time_text, g.photo_id, g.votes 
        FROM groups g
        JOIN subjects s ON g.subject_id = s.id
        JOIN teachers t ON g.teacher_id = t.id
        JOIN days d ON g.day_id = d.id
        WHERE g.subject_id = ? AND g.teacher_id = ?
    """, (sub_id, teach_id))
    groups = cursor.fetchall()
    conn.close()

    await call.message.delete()
    for g in groups:
        g_id, s_name, t_name, d_name, time_txt, photo_id, votes = g
        caption = f"📌 **Guruh:** {s_name}\n👨‍🏫 **Ustoz:** {t_name}\n📅 **Kunlar:** {d_name}\n⏰ **Soat:** {time_txt}\n🗳 **Ovozlar:** {votes}"
        kbd = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Guruhga Ovoz Berish", callback_data=f"vote_group_{g_id}")]
        ])
        await call.message.answer_photo(photo=photo_id, caption=caption, reply_markup=kbd)

@dp.callback_query(F.data.startswith("vote_group_"))
async def confirm_vote_dialog(call: CallbackQuery, state: FSMContext):
    g_id = int(call.data.split("_")[2])
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.name, t.name FROM groups g
        JOIN subjects s ON g.subject_id = s.id
        JOIN teachers t ON g.teacher_id = t.id
        WHERE g.id = ?
    """, (g_id,))
    res = cursor.fetchone()
    conn.close()

    g_name = f"{res[0]} ({res[1]})"
    await state.update_data(vote_group_id=g_id, g_name=g_name)

    kbd = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ha", callback_data="confirm_vote_yes"),
         InlineKeyboardButton(text="Yo'q", callback_data="confirm_vote_no")]
    ])
    await call.message.answer(f"Rostan ham **{g_name}** guruhiga ovoz bermoqchimisiz?", reply_markup=kbd)

@dp.callback_query(F.data == "confirm_vote_no")
async def cancel_vote(call: CallbackQuery, state: FSMContext):
    await call.message.delete()
    await call.message.answer("Ovoz berish bekor qilindi. Qayta tanlashingiz mumkin.", reply_markup=main_user_kb())

@dp.callback_query(F.data == "confirm_vote_yes")
async def process_vote(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    g_id = data.get('vote_group_id')
    g_name = data.get('g_name')
    user_id = call.from_user.id

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id FROM votes WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        conn.close()
        return await call.message.edit_text("Siz allaqachon ovoz bergansiz!")

    cursor.execute("INSERT INTO votes (user_id, group_id) VALUES (?, ?)", (user_id, g_id))
    cursor.execute("UPDATE groups SET votes = votes + 1 WHERE id = ?", (g_id,))
    cursor.execute("SELECT votes FROM groups WHERE id = ?", (g_id,))
    new_votes = cursor.fetchone()[0]
    
    conn.commit()
    conn.close()

    await call.message.edit_text(f"Tabriklayman, siz **{g_name}** guruhiga ovoz berdingiz, endi ushbu guruhda **{new_votes}** ta ovoz bor.")
    await state.clear()

# ==================== ADMIN HANDLERS ====================
@dp.message(Command("dev"))
async def admin_dev_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Admin panelga kirish uchun parolni kiriting:")
    await state.set_state(AdminStates.waiting_code)

@dp.message(AdminStates.waiting_code)
async def check_admin_code(message: Message, state: FSMContext):
    if message.text == ADMIN_CODE:
        await state.set_state(AdminStates.in_admin)
        await message.answer("Xush kelibsiz Admin!", reply_markup=admin_main_kb())
    else:
        await message.answer("Kod noto'g'ri!")
        await state.clear()

# GURUH QO'SHISH (STEP-BY-STEP WITH BACK & CANCEL)
@dp.message(F.text == "➕ Guruh qo'shish")
async def add_group_start(message: Message, state: FSMContext):
    await state.clear()
    await show_add_group_subject(message, state)

async def show_add_group_subject(target_event, state: FSMContext):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subjects")
    subjects = cursor.fetchall()
    conn.close()

    if not subjects:
        msg = "Avval Settings bo'limida fan qo'shing!"
        if isinstance(target_event, CallbackQuery):
            return await target_event.message.answer(msg, reply_markup=admin_main_kb())
        return await target_event.answer(msg, reply_markup=admin_main_kb())

    kbd_list = [[InlineKeyboardButton(text=s[1], callback_data=f"adm_sub_{s[0]}")] for s in subjects]
    kbd_list.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_cancel_add_group")])
    kbd = InlineKeyboardMarkup(inline_keyboard=kbd_list)

    if isinstance(target_event, CallbackQuery):
        await target_event.message.edit_text("Fan/tilni tanlang:", reply_markup=kbd)
    else:
        await target_event.answer("Fan/tilni tanlang:", reply_markup=kbd)
    await state.set_state(AdminStates.add_group_subject)

@dp.callback_query(F.data.startswith("adm_sub_"), AdminStates.add_group_subject)
async def add_group_sub_cb(call: CallbackQuery, state: FSMContext):
    sub_id = int(call.data.split("_")[2])
    await state.update_data(sub_id=sub_id)
    await show_add_group_teacher(call, state)

async def show_add_group_teacher(call: CallbackQuery, state: FSMContext):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM teachers")
    teachers = cursor.fetchall()
    conn.close()

    kbd_list = [[InlineKeyboardButton(text=t[1], callback_data=f"adm_teach_{t[0]}")] for t in teachers]
    kbd_list.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_back_to_sub"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_cancel_add_group")
    ])
    kbd = InlineKeyboardMarkup(inline_keyboard=kbd_list)

    await call.message.edit_text("Ustozni tanlang:", reply_markup=kbd)
    await state.set_state(AdminStates.add_group_teacher)

@dp.callback_query(F.data == "adm_back_to_sub", AdminStates.add_group_teacher)
async def back_to_sub_cb(call: CallbackQuery, state: FSMContext):
    await show_add_group_subject(call, state)

@dp.callback_query(F.data.startswith("adm_teach_"), AdminStates.add_group_teacher)
async def add_group_teach_cb(call: CallbackQuery, state: FSMContext):
    teach_id = int(call.data.split("_")[2])
    await state.update_data(teach_id=teach_id)
    await show_add_group_day(call, state)

async def show_add_group_day(call: CallbackQuery, state: FSMContext):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM days")
    days = cursor.fetchall()
    conn.close()

    kbd_list = [[InlineKeyboardButton(text=d[1], callback_data=f"adm_day_{d[0]}")] for d in days]
    kbd_list.append([
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_back_to_teach"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adm_cancel_add_group")
    ])
    kbd = InlineKeyboardMarkup(inline_keyboard=kbd_list)

    await call.message.edit_text("Dars kunlarini tanlang:", reply_markup=kbd)
    await state.set_state(AdminStates.add_group_day)

@dp.callback_query(F.data == "adm_back_to_teach", AdminStates.add_group_day)
async def back_to_teach_cb(call: CallbackQuery, state: FSMContext):
    await show_add_group_teacher(call, state)

@dp.callback_query(F.data.startswith("adm_day_"), AdminStates.add_group_day)
async def add_group_day_cb(call: CallbackQuery, state: FSMContext):
    day_id = int(call.data.split("_")[2])
    await state.update_data(day_id=day_id)

    await call.message.delete()
    await call.message.answer("Dars soatini kiriting (masalan: 14:00 - 16:00):", reply_markup=cancel_reply_kb())
    await state.set_state(AdminStates.add_group_time)

@dp.message(AdminStates.add_group_time)
async def add_group_time_msg(message: Message, state: FSMContext):
    await state.update_data(time_text=message.text)
    await message.answer("Guruh rasmini kiriting (Rasm shaklida yuboring):", reply_markup=cancel_reply_kb())
    await state.set_state(AdminStates.add_group_photo)

@dp.message(F.photo, AdminStates.add_group_photo)
async def add_group_photo_msg(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO groups (subject_id, teacher_id, day_id, time_text, photo_id)
        VALUES (?, ?, ?, ?, ?)
    """, (data['sub_id'], data['teach_id'], data['day_id'], data['time_text'], photo_id))
    conn.commit()
    conn.close()

    await message.answer("Guruh muvaffaqiyatli qo'shildi!", reply_markup=admin_main_kb())
    await state.set_state(AdminStates.in_admin)

@dp.callback_query(F.data == "adm_cancel_add_group")
async def cancel_add_group_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.in_admin)
    await call.message.delete()
    await call.message.answer("Guruh qo'shish bekor qilindi.", reply_markup=admin_main_kb())

@dp.callback_query(F.data.startswith("del_group_"))
async def delete_group_cb(call: CallbackQuery):
    g_id = int(call.data.split("_")[2])
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM groups WHERE id = ?", (g_id,))
    conn.commit()
    conn.close()
    await call.message.edit_text("Guruh o'chirib tashlandi.")

# SETTINGS SECTION & CRUD (Ustozlar, Fanlar, Kunlar)
@dp.message(F.text.in_(["👨‍🏫 Ustozlar", "📚 Fan va tillar", "📅 Dars kunlari"]))
async def manage_items(message: Message, state: FSMContext):
    await state.clear()
    
    table_map = {"👨‍🏫 Ustozlar": "teachers", "📚 Fan va tillar": "subjects", "📅 Dars kunlari": "days"}
    table = table_map[message.text]
    await state.update_data(current_table=table)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table}")
    items = cursor.fetchall()
    conn.close()

    kbd = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❌ {item[1]}", callback_data=f"delitem_{table}_{item[0]}")] for item in items
    ])
    
    await message.answer(
        f"Mavjud {message.text} ro'yxati (o'chirish uchun bosishingiz mumkin).\n\nYangi qo'shish uchun nomini text sifatida yuboring:",
        reply_markup=kbd
    )
    await state.set_state(AdminStates.manage_items)

@dp.callback_query(F.data.startswith("delitem_"))
async def delete_item_cb(call: CallbackQuery):
    _, table, item_id = call.data.split("_")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    await call.message.edit_text("Element o'chirildi.")

@dp.message(AdminStates.manage_items)
async def save_new_item(message: Message, state: FSMContext):
    data = await state.get_data()
    table = data.get("current_table")
    
    if table:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            cursor.execute(f"INSERT INTO {table} (name) VALUES (?)", (message.text,))
            conn.commit()
            await message.answer("Muvaffaqiyatli qo'shildi!", reply_markup=settings_kb())
        except sqlite3.IntegrityError:
            await message.answer("Bu nom allaqachon mavjud!")
        finally:
            conn.close()
    
    await state.set_state(AdminStates.in_admin)

# ==================== MAIN ====================
async def main():
    print("Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
