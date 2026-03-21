import asyncio, logging, os, hashlib
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# --- KONFIGURASI (WAJIB DIISI) ---
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
reff_col = db["referrals"]
pm_users_col = db["pm_users"]

user = Client("session_user", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("session_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- 1. BOT: GERBANG OTOMATIS (CATAT POIN & ARAHKAN) ---
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

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 LANJUT KE @WarungLENDIR_Robot", url=f"https://t.me/{PAYMENT_BOT}?start=start")],
        [InlineKeyboardButton("👩‍💻 CHAT ASISTEN (@belaa)", url=f"https://t.me/{ADMIN_USER}")]
    ])
    
    await msg.reply(
        "<b>SYNDICATE VIP ACCESS ✅</b>\n\nSilakan lanjut memesan di Bot Payment atau chat asisten kami.",
        reply_markup=btn
    )

# --- 2. USERBOT: PANEL MEMBER & ADMIN TOOLS ---
@user.on_message(filters.private & ~filters.me & ~filters.bot)
async def userbot_assistant(client, msg):
    u_id = msg.from_user.id
    text = (msg.text or "").lower().strip()

    # A. PANEL .REFF UNTUK MEMBER
    if text in [".reff", ".referral", "/reff"]:
        bot_me = await bot.get_me()
        link = f"https://t.me/{bot_me.username}?start=invite_{u_id}"
        data = await reff_col.find_one({"user_id": u_id})
        k = data.get("click_points", 0) if data else 0
        s = data.get("success_sales", 0) if data else 0
        
        await msg.reply(
            f"👑 **PANEL AFFILIATE**\n\nLink: <code>{link}</code>\n\n"
            f"📊 **STATISTIK:**\n• Klik: **{k}/{TARGET_KLIK}**\n• Sales: **{s}/{TARGET_SALES}**",
            parse_mode=ParseMode.HTML
        )
        return

    # B. LOGIKA FORWARD BUKTI TF
    if msg.photo:
        await pm_users_col.update_one({"user_id": u_id}, {"$set": {"waiting_payment": True, "last_interaction": datetime.now()}}, upsert=True)
        await msg.forward(PAYMENT_BOT)
        await msg.reply("🛡️ **Sedang diverifikasi...**")

# --- FITUR ADMIN KHUSUS KAKAK (@belaa) ---
@user.on_message(filters.command("cekreff", prefixes=".") & filters.me)
async def cek_reff_handler(client, msg):
    # Bisa pakai reply atau ketik ID: .cekreff 12345
    target_id = None
    if msg.reply_to_message:
        target_id = msg.reply_to_message.from_user.id
    elif len(msg.command) > 1:
        target_id = int(msg.command[1])
    else:
        return await msg.edit("Gunakan: `.cekreff [ID]` atau balas chat orangnya.")

    data = await reff_col.find_one({"user_id": target_id})
    if not data:
        return await msg.edit(f"❌ User `{target_id}` belum punya data referral.")
    
    k = data.get("click_points", 0)
    s = data.get("success_sales", 0)
    await msg.edit(f"📊 **DATA USER `{target_id}`**\n\n• Total Klik: **{k}**\n• Total Sales: **{s}**")

# --- 3. MONITORING SALES ---
@user.on_message(filters.chat(PAYMENT_BOT) & ~filters.me)
async def payment_checker(client, msg):
    text_bot = (msg.text or "").lower()
    buyer = await pm_users_col.find_one({"waiting_payment": True}, sort=[("last_interaction", -1)])
    if not buyer: return
    
    target_id = buyer["user_id"]
    if "t.me/+" in text_bot or "berhasil" in text_bot:
        await msg.copy(target_id)
        await pm_users_col.update_one({"user_id": target_id}, {"$set": {"waiting_payment": False}})

        if "invited_by" in buyer:
            inviter_id = buyer["invited_by"]
            res = await reff_col.find_one_and_update(
                {"user_id": inviter_id}, {"$inc": {"success_sales": 1}},
                upsert=True, return_document=True
            )
            s_count = res.get("success_sales", 0)
            if s_count >= TARGET_SALES:
                await user.send_message(inviter_id, "🎊 **GOAL! 3 SALES BERHASIL!** Chat @belaa untuk klaim VIP.")
                await reff_col.update_one({"user_id": inviter_id}, {"$set": {"success_sales": 0}})

async def main():
    await user.start(); await bot.start()
    print("🚀 SISTEM SYNDICATE ONLINE!"); await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
