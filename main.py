import asyncio, logging, os
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.enums import ParseMode

# --- KONFIGURASI ---
API_ID = int(os.getenv("API_ID", "38886457"))
API_HASH = os.getenv("API_HASH", "93ae4287da188cb3ba23a620c8ca5bd4")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8655576331:AAEL8MJraLvAxcmoevPjpNeU01id-ELriKM")
SESSION_STRING = os.getenv("SESSION_STRING")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Nadira31:Nadira31@cluster0.81zcrwl.mongodb.net/?appName=Cluster0")
PAYMENT_BOT = "WarungLENDIR_Robot"

m_client = AsyncIOMotorClient(MONGO_URI)
db = m_client["userbot_db"]
reff_col = db["referrals"]
pm_users_col = db["pm_users"]

user = Client("session_user", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("session_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- KONFIGURASI HADIAH ---
TARGET_KLIK = 100
TARGET_SALES = 3
HADIAH_VIP = """
🎁 **KLAIM HADIAH VIP GRATIS!**
Kamu berhasil membawa 3 pembeli sukses. Pilih 1 channel gratis:
1. [Link Channel A]
2. [Link Channel B]
"""

# --- 1. LOGIKA START & TRACKING KLIK ---
@bot.on_message(filters.command("start") & filters.private)
async def on_start_reff(client, msg):
    u_id = msg.from_user.id
    args = msg.text.split()
    
    if len(args) > 1 and "invite_" in args[1]:
        inviter_id = int(args[1].replace("invite_", ""))
        
        # Cek apakah user ini benar-benar baru di sistem
        is_user_exists = await pm_users_col.find_one({"user_id": u_id})
        
        if not is_user_exists and inviter_id != u_id:
            # SIMPAN TRACKING (Klik +1 & Siapa pengundangnya)
            res = await reff_col.find_one_and_update(
                {"user_id": inviter_id},
                {"$inc": {"click_points": 1}, "$push": {"clicked_by": u_id}},
                upsert=True, return_document=True
            )
            
            # Tandai pengundang di profil user baru (untuk tracking sales nanti)
            await pm_users_col.update_one(
                {"user_id": u_id},
                {"$set": {"invited_by": inviter_id, "reg_date": datetime.now()}},
                upsert=True
            )

            # Notifikasi Klik & Cek Target 100 Klik
            total_klik = res.get("click_points", 0)
            try:
                if total_klik == TARGET_KLIK:
                    await user.send_message(inviter_id, "🔥 **BOOM! 100 KLIK TERCAPAI!**\nKamu berhak dapat **DISKON 50%**. Chat admin sekarang!")
                elif total_klik % 10 == 0: # Notif setiap kelipatan 10 biar tidak spam
                    await user.send_message(inviter_id, f"📈 **Update Referral:** {total_klik}/{TARGET_KLIK} orang sudah klik linkmu!")
            except: pass

    # Registrasi user agar tidak dihitung klik berulang kali
    await pm_users_col.update_one({"user_id": u_id}, {"$set": {"is_active": True}}, upsert=True)
    await msg.reply("Halo! Gunakan bot ini untuk join VIP. Ketik `.myreff` di asisten untuk promo!")

# --- 2. LOGIKA PENJUALAN SUKSES (Sales +1) ---
@user.on_message(filters.chat(PAYMENT_BOT) & ~filters.me)
async def payment_handler(client, msg):
    text_bot = (msg.text or "").lower()
    
    # Ambil pembeli terakhir (Gunakan logika Queue DB yang kita buat tadi)
    buyer = await pm_users_col.find_one({"waiting_payment": True}, sort=[("last_interaction", -1)])
    if not buyer: return
    
    target_id = buyer["user_id"]

    if "t.me/+" in text_bot or "berhasil" in text_bot:
        await msg.copy(target_id)
        await pm_users_col.update_one({"user_id": target_id}, {"$set": {"waiting_payment": False}})

        # CEK APAKAH PEMBELI INI HASIL UNDANGAN
        if "invited_by" in buyer:
            inviter_id = buyer["invited_by"]
            
            # Tambah Poin Sales
            res_sales = await reff_col.find_one_and_update(
                {"user_id": inviter_id},
                {"$inc": {"success_sales": 1}},
                upsert=True, return_document=True
            )
            
            total_sales = res_sales.get("success_sales", 0)
            
            if total_sales >= TARGET_SALES:
                await user.send_message(inviter_id, HADIAH_VIP)
                await reff_col.update_one({"user_id": inviter_id}, {"$set": {"success_sales": 0}}) # Reset sales
            else:
                await user.send_message(inviter_id, f"💰 **Sales Berhasil!**\nTarget VIP Gratis: **{total_sales}/{TARGET_SALES}** pembeli.")

# --- 3. PANEL USER (.MYREFF) ---
@user.on_message(filters.private & ~filters.me)
async def user_panel(client, msg):
    text = (msg.text or "").lower()
    if text == ".myreff":
        u_id = msg.from_user.id
        bot_me = await bot.get_me()
        link = f"https://t.me/{bot_me.username}?start=invite_{u_id}"
        
        data = await reff_col.find_one({"user_id": u_id})
        k = data.get("click_points", 0) if data else 0
        s = data.get("success_sales", 0) if data else 0
        
        await msg.reply(
            f"🔗 **AFFILIATE PANEL**\n`{link}`\n\n"
            f"🚀 **MISI VIRAL:**\n"
            f"• Ajak 100 orang klik link: **{k}/100**\n"
            f"🎁 Hadiah: **Diskon 50%**\n\n"
            f"💰 **MISI SALES:**\n"
            f"• 3 Teman beli VIP: **{s}/3**\n"
            f"🎁 Hadiah: **VIP Gratis Pilihan**"
        )

# --- MAIN ---
async def main():
    await user.start(); await bot.start()
    print("🚀 SISTEM DUAL-REWARD AKTIF!"); await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
