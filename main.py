import re, asyncio, logging, os, hashlib, urllib.parse
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# --- CONFIGURATION ---
API_ID = int(os.getenv("API_ID", "38886457"))
API_HASH = os.getenv("API_HASH", "93ae4287da188cb3ba23a620c8ca5bd4")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8655576331:AAEL8MJraLvAxcmoevPjpNeU01id-ELriKM")
SESSION_STRING = os.getenv("SESSION_STRING")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Nadira31:Nadira31@cluster0.81zcrwl.mongodb.net/?appName=Cluster0")

PAYMENT_BOT = "WarungLENDIR_Robot"
ADMIN_USER = "belaa"
TARGET_KLIK = 100
TARGET_SALES = 3

logging.basicConfig(level=logging.INFO)

m_client = AsyncIOMotorClient(MONGO_URI)
db = m_client["userbot_db"]
notes_col = db["notes"]
pm_users_col = db["pm_users"]
config_col = db["config"]
hashes_col = db["processed_hashes"]
reff_col = db["referrals"]

user = Client("session_user", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("session_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- UTILS ---
async def get_config(key, default):
    res = await config_col.find_one({"key": key})
    return res["val"] if res else default

def format_html(text, user_obj):
    if not text: return ""
    name = user_obj.first_name or "Kakak"
    mention = f"<a href='tg://user?id={user_obj.id}'>{name}</a>"
    return text.replace("{mention}", mention).replace("{name}", name).replace("{id}", str(user_obj.id))

async def get_photo_hash(client, message):
    photo = await client.download_media(message, in_memory=True)
    return hashlib.md5(photo.getbuffer()).hexdigest()

# --- 1. BOT HANDLER (@ReferralVVIPbot) ---
@bot.on_message(filters.command("start") & filters.private)
async def bot_start_handler(client, msg):
    u_id = msg.from_user.id
    args = msg.text.split()
    
    # Logika Hitung Klik Referral
    if len(args) > 1 and "invite_" in args[1]:
        inviter_id = int(args[1].replace("invite_", ""))
        is_new = await pm_users_col.find_one({"user_id": u_id}) is None
        if is_new and inviter_id != u_id:
            await reff_col.update_one({"user_id": inviter_id}, {"$inc": {"click_points": 1}}, upsert=True)
            await pm_users_col.update_one({"user_id": u_id}, {"$set": {"invited_by": inviter_id}}, upsert=True)

    pesan_asisten = "Halo kak saya di undang teman untuk join vip"
    url_asisten = f"https://t.me/{ADMIN_USER}?text={urllib.parse.quote(pesan_asisten)}"
    
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 LANJUT KE @WarungLENDIR_Robot", url=f"https://t.me/{PAYMENT_BOT}?start=start")],
        [InlineKeyboardButton("👩‍💻 CHAT ASISTEN (@belaa)", url=url_asisten)]
    ])
    
    welcome_raw = await get_config("welcome_text", "<b>SYNDICATE VIP ACCESS ✅</b>\n\nSilakan klik tombol di bawah.")
    await msg.reply(format_html(welcome_raw, msg.from_user), reply_markup=btn)

# --- 2. USERBOT HANDLER (@belaa) ---
@user.on_message(filters.private & ~filters.me & ~filters.bot)
async def assistant_handler(client, msg):
    user_id = msg.from_user.id
    text = (msg.text or "").strip().lower()
    
    # 1. ABAIKAN CHAT TIDAK PENTING
    ignore_list = ["p", "kak", "min", "bang", "tes", "test", "halo", "oke", "makasih", "thanks"]
    if text in ignore_list or (text and len(text) < 2):
        return

    # 2. FITUR .REFF UNTUK MEMBER
    if text in [".reff", ".referral"]:
        bot_me = await bot.get_me()
        link = f"https://t.me/{bot_me.username}?start=invite_{user_id}"
        data = await reff_col.find_one({"user_id": user_id})
        k = data.get("click_points", 0) if data else 0
        s = data.get("success_sales", 0) if data else 0
        await msg.reply(f"👑 **PANEL AFFILIATE**\n\nLink: <code>{link}</code>\n\n📊 **Statistik:**\n• Klik: **{k}/{TARGET_KLIK}**\n• Sales: **{s}/{TARGET_SALES}**")
        return

    # 3. LOGIKA FOTO (ANTI-SPAM BUKTI TF)
    if msg.photo:
        f_hash = await get_photo_hash(client, msg)
        if await hashes_col.find_one({"hash": f_hash}):
            await msg.reply("⚠️ **Bukti transfer ini sudah pernah dikirim sebelumnya.**")
            return

        await hashes_col.insert_one({"hash": f_hash, "user_id": user_id, "date": datetime.now()})
        await pm_users_col.update_one({"user_id": user_id}, {"$set": {"waiting_payment": True, "last_interaction": datetime.now()}}, upsert=True)
        await msg.forward(PAYMENT_BOT)
        
        verif_raw = await get_config("verif_text", "Sabar ya {mention}, asisten sedang verifikasi...")
        await msg.reply(format_html(verif_raw, msg.from_user))
        return

    # 4. LOGIKA HARGA & AUTO PIN (USER BARU vs LAMA)
    tanya_harga = ["harga", "berapa", "price", "daftar", "list", "join", "vip", "halo kak saya di undang teman"]
    if any(x in text for x in tanya_harga):
        is_user_exists = await pm_users_col.find_one({"user_id": user_id})
        
        # Kirim Daftar Harga (Dari Note 'harga' di MongoDB Kakak)
        note_harga = await notes_col.find_one({"key": "harga"})
        if note_harga:
            text_harga = format_html(note_harga["value"], msg.from_user)
            res = await msg.reply(text_harga)
            
            if not is_user_exists:
                await res.pin(both_sides=True)
                await pm_users_col.update_one({"user_id": user_id}, {"$set": {"name": msg.from_user.first_name}}, upsert=True)
        else:
            await msg.reply("Daftar harga belum diatur di database.")
        return

# --- 3. MONITORING PAYMENT (@WarungLENDIR_Robot) ---
@user.on_message(filters.chat(PAYMENT_BOT) & ~filters.me)
async def payment_reply_handler(client, msg):
    text_bot = (msg.text or "").lower()
    buyer = await pm_users_col.find_one({"waiting_payment": True}, sort=[("last_interaction", -1)])
    if not buyer: return
    
    target_id = buyer["user_id"]
    if "t.me/+" in text_bot or "t.me/joinchat" in text_bot:
        sent_link = await msg.copy(target_id)
        await sent_link.pin(both_sides=True)
        
        thanks_raw = await get_config("thanks_text", "Berhasil!")
        await client.send_message(target_id, format_html(thanks_raw, await client.get_users(target_id)))
        await pm_users_col.update_one({"user_id": target_id}, {"$set": {"waiting_payment": False}})

        # HITUNG SALES UNTUK PENGUNDANG
        if "invited_by" in buyer:
            inviter = buyer["invited_by"]
            res = await reff_col.find_one_and_update(
                {"user_id": inviter}, {"$inc": {"success_sales": 1}},
                upsert=True, return_document=True
            )
            if res.get("success_sales", 0) >= TARGET_SALES:
                await user.send_message(inviter, "🎊 **GOAL! 3 SALES BERHASIL!** Hubungi @belaa untuk VIP.")
                await reff_col.update_one({"user_id": inviter}, {"$set": {"success_sales": 0}})

async def main():
    await user.start(); await bot.start()
    print("🚀 SISTEM STABIL & REFERRAL AKTIF!"); await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
