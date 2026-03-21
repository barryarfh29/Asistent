import asyncio, logging, os, hashlib
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# --- KONFIGURASI (WAJIB DIISI) ---
API_ID = int(os.getenv("API_ID", "38886457"))
API_HASH = os.getenv("API_HASH", "93ae4287da188cb3ba23a620c8ca5bd4")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8655576331:AAEL8MJraLvAxcmoevPjpNeU01id-ELriKM") # Token Bot Asisten Kakak
SESSION_STRING = os.getenv("SESSION_STRING")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Nadira31:Nadira31@cluster0.81zcrwl.mongodb.net/?appName=Cluster0")

# Target Username
PAYMENT_BOT = "WarungLENDIR_Robot"
ADMIN_USER = "belaa"

# Aturan Hadiah
TARGET_KLIK = 100
TARGET_SALES = 3

logging.basicConfig(level=logging.INFO)
m_client = AsyncIOMotorClient(MONGO_URI)
db = m_client["userbot_db"]
reff_col = db["referrals"]
pm_users_col = db["pm_users"]
hashes_col = db["processed_hashes"]

user = Client("session_user", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("session_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- 1. LOGIKA BOT (PINTU MASUK REFERRAL) ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, msg):
    u_id = msg.from_user.id
    args = msg.text.split()
    
    # Cek jika masuk lewat link invite
    if len(args) > 1 and "invite_" in args[1]:
        inviter_id = int(args[1].replace("invite_", ""))
        
        # Cek apakah ini user baru murni
        is_new = await pm_users_col.find_one({"user_id": u_id}) is None
        
        if is_new and inviter_id != u_id:
            # +1 Klik Poin untuk Pengundang
            res = await reff_col.find_one_and_update(
                {"user_id": inviter_id},
                {"$inc": {"click_points": 1}},
                upsert=True, return_document=True
            )
            # Simpan data siapa yang mengundang user ini
            await pm_users_col.update_one(
                {"user_id": u_id},
                {"$set": {"invited_by": inviter_id, "join_date": datetime.now()}},
                upsert=True
            )
            # Notif ke pengundang jika mencapai 100 klik
            if res.get("click_points") == TARGET_KLIK:
                try: await user.send_message(inviter_id, "🔥 **MISI VIRAL SELESAI!**\n100 Orang klik linkmu. Kamu dapat **DISKON 50%**.")
                except: pass

    # Tampilan Menu dengan Tombol ke @WarungLENDIR_Robot
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 ORDER VIA @WarungLENDIR_Robot", url=f"https://t.me/{PAYMENT_BOT}")],
        [InlineKeyboardButton("👩‍💻 CHAT ASISTEN @belaa", url=f"https://t.me/{ADMIN_USER}")],
        [InlineKeyboardButton("🎁 CEK STATUS REFF", callback_data="none")]
    ])
    
    await msg.reply(
        "<b>SYNDICATE VIP ACCESS</b>\n\n"
        "Gunakan tombol di bawah untuk memesan VIP atau bertanya pada asisten.",
        reply_markup=btn
    )

# --- 2. LOGIKA USERBOT (PANEL REFF & TRACKING) ---
@user.on_message(filters.private & ~filters.me & ~filters.bot)
async def userbot_assistant(client, msg):
    u_id = msg.from_user.id
    text = (msg.text or "").lower().strip()

    # Perintah memunculkan link referral
    if text in [".reff", ".referral", "/reff", "/referral"]:
        bot_me = await bot.get_me()
        link = f"https://t.me/{bot_me.username}?start=invite_{u_id}"
        data = await reff_col.find_one({"user_id": u_id})
        k = data.get("click_points", 0) if data else 0
        s = data.get("success_sales", 0) if data else 0
        
        panel = (
            f"👑 **PANEL AFFILIATE SYNDICATE**\n\n"
            f"Link Undangan:\n<code>{link}</code>\n\n"
            f"📊 **PROGRES ANDA:**\n"
            f"• Klik Viral: **{k}/{TARGET_KLIK}**\n"
            f"• Sales Berhasil: **{s}/{TARGET_SALES}**\n\n"
            f"<i>Poin sales hanya masuk jika temanmu transaksi lewat asisten ini.</i>"
        )
        await msg.reply(panel, parse_mode=ParseMode.HTML)
        return

    # Logika Kirim Bukti (Foto)
    if msg.photo:
        # Tandai user sedang dalam proses bayar
        await pm_users_col.update_one(
            {"user_id": u_id},
            {"$set": {"waiting_payment": True, "last_interaction": datetime.now()}},
            upsert=True
        )
        # Teruskan ke Bot Payment
        await msg.forward(PAYMENT_BOT)
        await msg.reply("🛡️ **Bukti terkirim!** Sedang dicek oleh system.")

# --- 3. LOGIKA TRACKING SALES (DARI @WarungLENDIR_Robot) ---
@user.on_message(filters.chat(PAYMENT_BOT) & ~filters.me)
async def payment_checker(client, msg):
    text_bot = (msg.text or "").lower()
    
    # Ambil pembeli yang terakhir kirim bukti
    buyer = await pm_users_col.find_one({"waiting_payment": True}, sort=[("last_interaction", -1)])
    if not buyer: return
    
    target_id = buyer["user_id"]

    # Jika Bot Payment kasih Link VIP (Artinya Bayar Berhasil)
    if "t.me/+" in text_bot or "t.me/joinchat" in text_bot:
        # Kirim Link ke Pembeli
        await msg.copy(target_id)
        # Matikan status waiting
        await pm_users_col.update_one({"user_id": target_id}, {"$set": {"waiting_payment": False}})

        # CEK APAKAH PEMBELI INI HASIL UNDANGAN
        if "invited_by" in buyer:
            inviter_id = buyer["invited_by"]
            
            # +1 Poin Sales Sukses
            res_sales = await reff_col.find_one_and_update(
                {"user_id": inviter_id},
                {"$inc": {"success_sales": 1}},
                upsert=True, return_document=True
            )
            
            s_count = res_sales.get("success_sales", 0)
            
            if s_count >= TARGET_SALES:
                # Milestone 3 Sales Tercapai
                await user.send_message(inviter_id, "🎊 **GOAL! 3 SALES BERHASIL!**\nSelamat, kamu dapat 1 Channel VIP Gratis. Hubungi admin @belaa.")
                await reff_col.update_one({"user_id": inviter_id}, {"$set": {"success_sales": 0}})
            else:
                await user.send_message(inviter_id, f"💰 **Sales Sukses!**\nTemanmu join VIP. Progres: **{s_count}/{TARGET_SALES}**")

# --- RUN ---
async def main():
    await user.start()
    await bot.start()
    print("🚀 ASISTEN @WarungLENDIR_Robot & @belaa AKTIF!")
    await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
