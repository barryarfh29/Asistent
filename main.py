import re, asyncio, logging, os, random
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    InlineQueryResultArticle, InlineQueryResultCachedPhoto,
    InputTextMessageContent
)
from pyrogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- CONFIGURATION (ENV) ---
API_ID = int(os.getenv("API_ID", "38886457"))
API_HASH = os.getenv("API_HASH", "93ae4287da188cb3ba23a620c8ca5bd4")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8655576331:AAEL8MJraLvAxcmoevPjpNeU01id-ELriKM")
SESSION_STRING = os.getenv("SESSION_STRING")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Nadira31:Nadira31@cluster0.81zcrwl.mongodb.net/?appName=Cluster0")
PAYMENT_BOT = "WarungLENDIR_Robot" 

logging.basicConfig(level=logging.INFO)

m_client = AsyncIOMotorClient(MONGO_URI)
db = m_client["userbot_db"]
notes_col = db["notes"]
pm_users_col = db["pm_users"]
config_col = db["config"]

user = Client("session_user", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("session_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Variabel Global Memory
last_active_buyer = None 

# --- AUTO RESET SETIAP 2 HARI ---
async def reset_buyer_data():
    global last_active_buyer
    last_active_buyer = None
    logging.info("🧹 AUTO RESET: Memory pembeli dibersihkan.")

scheduler = AsyncIOScheduler()
scheduler.add_job(reset_buyer_data, "interval", days=2)

# --- HELPER FUNCTIONS ---
async def get_config(key, default):
    res = await config_col.find_one({"key": key})
    return res["val"] if res else default

def format_html(text, user_obj):
    if not text: return ""
    name = user_obj.first_name or "Kakak"
    mention = f"<a href='tg://user?id={user_obj.id}'>{name}</a>"
    return text.replace("{mention}", mention).replace("{name}", name).replace("{id}", str(user_obj.id))

async def auto_click(client, chat_id, button_text):
    async for msg in client.get_chat_history(chat_id, limit=1):
        if msg.reply_markup:
            for row in msg.reply_markup.inline_keyboard:
                for btn in row:
                    if button_text.lower() in btn.text.lower():
                        try:
                            await asyncio.wait_for(msg.click(btn.text), timeout=3)
                            return True
                        except: return True
    return False

async def get_bot_file_id(message):
    try:
        photo_buffer = await user.download_media(message, in_memory=True)
        photo_buffer.name = "photo.jpg"
        sent = await bot.send_photo(chat_id="me", photo=photo_buffer)
        return sent.photo.file_id
    except: return None

def parse_buttons(text):
    if not text: return []
    btns, row = [], []
    pattern = r"\[(.*?)\]\(buttonurl:(.*?)(?::(same))?\)"
    for m in re.finditer(pattern, text):
        label, url, same = m.group(1), m.group(2).strip(), m.group(3) == "same"
        b = InlineKeyboardButton(label, url=url)
        if same and row: row.append(b)
        else:
            if row: btns.append(row)
            row = [b]
    if row: btns.append(row)
    return btns

# --- LOGIKA UTAMA ASISTEN ---

@user.on_message(filters.private & ~filters.me & ~filters.bot)
async def assistant_handler(client, msg):
    global last_active_buyer
    user_id = msg.from_user.id
    text = msg.text.strip().lower() if msg.text else ""
    await pm_users_col.update_one({"user_id": user_id}, {"$set": {"name": msg.from_user.first_name}}, upsert=True)

    # 1. Foto Bukti Transfer
    if msg.photo:
        verif_raw = await get_config("verif_text", "none")
        if verif_raw.lower() != "none":
            await msg.reply(format_html(verif_raw, msg.from_user), parse_mode=ParseMode.HTML)
        
        last_active_buyer = user_id # Tandai pembeli aktif
        await msg.forward(PAYMENT_BOT)
        return

    # 2. Tagih Bukti Transfer
    tagih_keywords = ["lunas", "sudah bayar", "done", "tf", "transfer", "cek"]
    if any(x in text for x in tagih_keywords) and not msg.photo:
        await msg.reply(format_html("Mohon maaf {mention}, tolong lampirkan <b>Foto Bukti Transfernya</b> agar asisten bisa bantu proses ya 🙏", msg.from_user), parse_mode=ParseMode.HTML)
        return

    # 3. Filter Harga
    produk_list = ["hijab", "indo", "smp", "sma", "baru", "payment", "satuan", "hemat", "premium", "skandal", "super", "record", "baratt", "fans"]
    tanya_umum = ["halo", "join", "berapa", "price", "daftar", "list", "mau", "kak", "min", "p", "vip", "info"]
    
    is_new = await pm_users_col.count_documents({"user_id": user_id}) <= 1
    is_order = any(x in text for x in produk_list)
    is_tanya = any(x in text for x in tanya_umum) or (msg.sticker and is_new)

    if is_tanya and not is_order:
        note_harga = await notes_col.find_one({"key": "harga"})
        if note_harga:
            bot_me = await bot.get_me()
            inline = await user.get_inline_bot_results(bot_me.username, "harga")
            if inline.results:
                await user.send_inline_bot_result(msg.chat.id, inline.query_id, inline.results[0].id)
                return

    # 4. Auto Search Paket
    if text and is_order and len(text) < 40:
        p1 = await msg.reply(f"🔍 **Cek paket: {msg.text.upper()}**")
        stop_animation = False
        async def play_animation():
            frames = ["● ○ ○ ○", "○ ● ○ ○", "○ ○ ● ○", "○ ○ ○ ●"]
            idx = 0
            while not stop_animation:
                try:
                    await p1.edit(f"🔍 **Cek paket: {msg.text.upper()} {frames[idx % len(frames)]}**")
                    idx += 1; await asyncio.sleep(0.5)
                except: break
        
        animation_task = asyncio.create_task(play_animation())
        await client.send_message(PAYMENT_BOT, "/start")
        await asyncio.sleep(1)
        
        found = False
        if await auto_click(client, PAYMENT_BOT, "VIP SATUAN"):
            await asyncio.sleep(0.7)
            if await auto_click(client, PAYMENT_BOT, msg.text): found = True
        
        if not found:
            await client.send_message(PAYMENT_BOT, "/start")
            await asyncio.sleep(0.7)
            if await auto_click(client, PAYMENT_BOT, "PAKET HEMAT"):
                await asyncio.sleep(0.7)
                if await auto_click(client, PAYMENT_BOT, msg.text): found = True

        stop_animation = True
        animation_task.cancel()

        if found:
            await asyncio.sleep(0.5); await auto_click(client, PAYMENT_BOT, "Gabung Sekarang")
            await p1.edit("✅ **Paket ditemukan!**\nSedang menyiapkan QR Code...")
            for _ in range(15):
                await asyncio.sleep(1)
                async for qr_msg in client.get_chat_history(PAYMENT_BOT, limit=1):
                    if qr_msg.photo:
                        await qr_msg.copy(msg.chat.id)
                        await p1.delete()
                        await msg.reply(format_html("✅ <b>Silakan Transfer {mention}.</b>\nKirim Bukti Transfer jika sudah.", msg.from_user), parse_mode=ParseMode.HTML)
                        return
        else:
            await p1.edit("❌ **Gagal!** Paket tidak ditemukan.")
            await asyncio.sleep(2); await p1.delete()

# --- HANDLER BALASAN BOT PAYMENT ---

@user.on_message(filters.chat(PAYMENT_BOT) & ~filters.me)
async def payment_reply_handler(client, msg):
    global last_active_buyer
    if not last_active_buyer: return

    try:
        target_id = last_active_buyer
        text_bot = (msg.text or "").lower()
        u_data = await client.get_users(target_id)

        if any(x in text_bot for x in ["gagal", "tidak ditemukan", "belum masuk", "nominal salah", "expired"]):
            await client.send_message(target_id, format_html("Maaf kak {mention}, pembayaran belum masuk. Mohon cek ulang nominal ya 🙏", u_data), parse_mode=ParseMode.HTML)
        else:
            await msg.copy(target_id) # Forward Link VIP
            thanks_raw = await get_config("thanks_text", "none")
            if thanks_raw.lower() != "none":
                await client.send_message(target_id, format_html(thanks_raw, u_data), parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Error: {e}")

# --- ADMIN COMMANDS ---

@user.on_message(filters.command("help", prefixes=".") & filters.me)
async def cmd_help(_, msg):
    help_text = "<b>📂 ADMIN ASISTEN</b>\n\n• <code>.settextharga</code>\n• <code>.setharga</code> (reply foto)\n• <code>.setverif</code>\n• <code>.setthanks</code>\n• <code>.save [nama]</code>\n• <code>.notes</code>\n• <code>.resetpembeli</code>\n• <code>.broadcast</code> (reply)"
    await msg.edit(help_text, parse_mode=ParseMode.HTML)

@user.on_message(filters.command("resetpembeli", prefixes=".") & filters.me)
async def cmd_res(_, msg):
    global last_active_buyer
    last_active_buyer = None
    await msg.edit("🗑️ Memory pembeli dibersihkan!")

@user.on_message(filters.command("setverif", prefixes=".") & filters.me)
async def cmd_setverif(_, msg):
    txt = msg.text.split(maxsplit=1)[1] if len(msg.text.split()) > 1 else "none"
    await config_col.update_one({"key": "verif_text"}, {"$set": {"val": txt}}, upsert=True)
    await msg.edit("✅ Pesan Verifikasi Diset!")

@user.on_message(filters.command("setthanks", prefixes=".") & filters.me)
async def cmd_setthanks(_, msg):
    txt = msg.text.split(maxsplit=1)[1] if len(msg.text.split()) > 1 else "none"
    await config_col.update_one({"key": "thanks_text"}, {"$set": {"val": txt}}, upsert=True)
    await msg.edit("✅ Pesan Terima Kasih Diset!")

@user.on_message(filters.command("save", prefixes=".") & filters.me)
async def cmd_save(_, msg):
    parts = msg.text.split(maxsplit=2)
    if len(parts) < 2: return
    key, content = parts[1].lower(), (parts[2] if len(parts) > 2 else "")
    f_id = await get_bot_file_id(msg.reply_to_message or msg)
    await notes_col.update_one({"key": key}, {"$set": {"file_id": f_id, "content": content}}, upsert=True)
    await msg.edit(f"✅ Note <code>{key}</code> Disimpan!")

@user.on_message(filters.command("broadcast", prefixes=".") & filters.me)
async def cmd_broadcast(_, msg):
    if not msg.reply_to_message: return await msg.edit("❌ Reply ke pesan!")
    await msg.edit("⌛ Broadcasting..."); count = 0
    async for u in pm_users_col.find():
        try:
            await msg.reply_to_message.copy(u["user_id"])
            count += 1; await asyncio.sleep(0.1)
        except: pass
    await msg.edit(f"✅ Broadcast Selesai! Terkirim ke {count} user.")

# --- INLINE HANDLER ---
@bot.on_inline_query()
async def inline_handler(_, query):
    note = await notes_col.find_one({"key": query.query.lower().strip()})
    if not note: return
    raw = note.get("content", "")
    txt_formatted = format_html(raw, query.from_user)
    kb = InlineKeyboardMarkup(parse_buttons(txt_formatted)) if parse_buttons(txt_formatted) else None
    txt_final = re.sub(r"\[.*?\]\(buttonurl:.*?\)", "", txt_formatted)
    res = []
    if note.get("file_id"):
        res.append(InlineQueryResultCachedPhoto(id=os.urandom(4).hex(), photo_file_id=note["file_id"], caption=txt_final, parse_mode=ParseMode.HTML, reply_markup=kb))
    else:
        res.append(InlineQueryResultArticle(id=os.urandom(4).hex(), title="Note", input_message_content=InputTextMessageContent(txt_final, parse_mode=ParseMode.HTML), reply_markup=kb))
    await query.answer(res, cache_time=1)

async def main():
    scheduler.start()
    await user.start(); await bot.start()
    print("🚀 ASISTEN SIAP TEMPUR!"); await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())








saya ingin menjelajahi code saya inin 
