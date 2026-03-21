import asyncio, logging, os, urllib.parse
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# --- KONFIGURASI (PASTIKAN SUDAH BENAR) ---
API_ID = int(os.getenv("API_ID", "38886457"))
API_HASH = os.getenv("API_HASH", "93ae4287da188cb3ba23a620c8ca5bd4")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8655576331:AAEL8MJraLvAxcmoevPjpNeU01id-ELriKM")
SESSION_STRING = os.getenv("SESSION_STRING")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Nadira31:Nadira31@cluster0.81zcrwl.mongodb.net/?appName=Cluster0")

PAYMENT_BOT = "WarungLENDIR_Robot"
ADMIN_USER = "belaa"

logging.basicConfig(level=logging.INFO)
m_client = AsyncIOMotorClient(MONGO_URI)
db = m_client["userbot_db"]
reff_col = db["referrals"]
pm_users_col = db["pm_users"]
config_col = db["config"]

user = Client("session_user", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("session_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- UTILS: AMBIL DATA DARI MONGO ---
async def get_config(key, default_text):
    res = await config_col.find_one({"key": key})
    return res["val"] if res else default_text

# --- 1. BOT HANDLER (@ReferralVVIPbot) ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, msg):
    u_id = msg.from_user.id
    args = msg.text.split()
    
    if len(args) > 1 and "invite_" in args[1]:
        inviter_id = int(args[1].replace("invite_", ""))
        is_new = await pm_users_col.find_one({"user_id": u_id}) is None
        if is_new and inviter_id != u_id:
            await reff_col.update_one({"user_id": inviter_id}, {"$inc": {"click_points": 1}}, upsert=True)
            await pm_users_col.update_one({"user_id": u_id}, {"$set": {"invited_by": inviter_id}}, upsert=True)

    welcome_text = await get_config("welcome_msg", "<b>SYNDICATE VIP ACCESS ✅</b>\nKlik tombol di bawah untuk lanjut.")
    pesan_asisten = "Halo kak saya di undang teman untuk join vip"
    url_asisten = f"https://t.me/{ADMIN_USER}?text={urllib.parse.quote(pesan_asisten)}"
    
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 LANJUT KE @WarungLENDIR_Robot", url=f"https://t.me/{PAYMENT_BOT}?start=start")],
        [InlineKeyboardButton("👩‍💻 CHAT ASISTEN (@belaa)", url=url_asisten)]
    ])
    await msg.reply(welcome_text, reply_markup=btn)

# --- 2. USERBOT HANDLER (@belaa) ---

# FITUR HELP ADMIN
@user.on_message(filters.me & filters.command("help", prefixes="."))
async def help_handler(client, msg):
    text = (
        "👑 **SYNDICATE ADMIN HELP**\n\n"
        "• `.reff` - Cek link & statistik milikmu\n"
        "• `.cekreff [ID/Reply]` - Cek poin member\n"
        "• `.setharga [Teks]` - Atur daftar harga VIP\n"
        "• `.setthanks [Teks]` - Atur ucapan terima kasih\n"
        "• `.setwelcome [Teks]` - Atur sambutan bot\n"
        "• `.broadcast [Teks]` - Kirim pesan ke semua member\n"
    )
    await msg.edit(text)

# FITUR SETTING (SAVE KE MONGO)
@user.on_message(filters.me & filters.command(["setharga", "setthanks", "setwelcome"], prefixes="."))
async def settings_handler(client, msg):
    cmd = msg.command[0]
    if len(msg.command) < 2: return await msg.edit(f"Format: `.{cmd} [Teks]`")
    key_map = {"setharga": "price_list", "setthanks": "thanks_msg", "setwelcome": "welcome_msg"}
    text = msg.text.split(None, 1)[1]
    await config_col.update_one({"key": key_map[cmd]}, {"$set": {"val": text}}, upsert=True)
    await msg.edit(f"✅ **Update Berhasil!**")

# FITUR CEK REFF MEMBER
@user.on_message(filters.me & filters.command("cekreff", prefixes="."))
async def cek_reff_handler(client, msg):
    target_id = msg.reply_to_message.from_user.id if msg.reply_to_message else (int(msg.command[1]) if len(msg.command) > 1 else None)
    if not target_id: return await msg.edit("Reply chat atau gunakan ID.")
    data = await reff_col.find_one({"user_id": target_id})
    if not data: return await msg.edit("❌ Tidak ada data.")
    await msg.edit(f"📊 **USER `{target_id}`**\n• Klik: **{data.get('click_points', 0)}**\n• Sales: **{data.get('success_sales', 0)}**")

# FITUR .REFF UNTUK MEMBER AMBIL LINK
@user.on_message(filters.private & ~filters.me & ~filters.bot)
async def userbot_main_handler(client, msg):
    u_id = msg.from_user.id
    text = (msg.text or "").lower().strip()

    if text in [".reff", ".referral"]:
        bot_info = await bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=invite_{u_id}"
        data = await reff_col.find_one({"user_id": u_id})
        k, s = (data.get('click_points', 0), data.get('success_sales', 0)) if data else (0, 0)
        await msg.reply(f"👑 **PANEL AFFILIATE**\nLink: <code>{link}</code>\n📊 Klik: **{k}/100** | Sales: **{s}/3**")
        return

    # LOGIKA AUTO-REPLY HARGA (SANGAT PEKA)
    keywords = ["halo kak saya di undang teman untuk join vip", "harga", "price", "daftar", "vip"]
    if any(k in text for k in keywords):
        harga = await get_config("price_list", "Daftar harga belum diatur.")
        await msg.reply(harga)
        return

    # LOGIKA WELCOME UNTUK CHAT PERTAMA KALI
    is_old = await pm_users_col.find_one({"user_id": u_id})
    if not is_old:
        harga = await get_config("price_list", "Selamat datang!\n\nSilakan cek harga di bawah ini.")
        await msg.reply(harga)
        await pm_users_col.update_one({"user_id": u_id}, {"$set": {"join_date": datetime.now()}}, upsert=True)
        return

    # FORWARD BUKTI TF
    if msg.photo:
        await pm_users_col.update_one({"user_id": u_id}, {"$set": {"waiting_payment": True, "last_interaction": datetime.now()}}, upsert=True)
        await msg.forward(PAYMENT_BOT)
        await msg.reply("🛡️ **Sedang diverifikasi...**")

# --- 3. MONITORING SALES ---
@user.on_message(filters.chat(PAYMENT_BOT) & ~filters.me)
async def payment_monitor(client, msg):
    text_bot = (msg.text or "").lower()
    buyer = await pm_users_col.find_one({"waiting_payment": True}, sort=[("last_interaction", -1)])
    if not buyer: return
    if "t.me/+" in text_bot or "berhasil" in text_bot:
        thanks = await get_config("thanks_msg", "Pembayaran berhasil!")
        await user.send_message(buyer["user_id"], thanks)
        await msg.copy(buyer["user_id"])
        await pm_users_col.update_one({"user_id": buyer["user_id"]}, {"$set": {"waiting_payment": False}})
        if "invited_by" in buyer:
            await reff_col.update_one({"user_id": buyer["invited_by"]}, {"$inc": {"success_sales": 1}}, upsert=True)

async def main():
    await user.start(); await bot.start()
    print("🚀 SISTEM FINAL RUNNING!"); await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
