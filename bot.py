import os
import logging
import requests
import asyncio
from datetime import datetime, timedelta
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# লোগিং সেটআপ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# কনফিগারেশন
TOKEN = os.getenv("BOT_TOKEN")
FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL") 
PREMIUM_CHANNEL_ID = os.getenv("PREMIUM_CHANNEL_ID") 
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MONGO_URI = os.getenv("MONGO_URI")

# পেমেন্ট গেটওয়ে ক্রেমেনশিয়ালস
SECRET_KEY = os.getenv("SECRET_KEY")
MERCHANT_ID = os.getenv("MERCHANT_ID")
API_KEY = os.getenv("API_KEY")

# মঙ্গোডিবি কানেকশন
client = MongoClient(MONGO_URI)
db = client['telegram_premium_bot']
users_collection = db['users']

PLAN_PRICES = {
    "1d": {"days": 1, "price": 10, "name": "১ দিন"},
    "2d": {"days": 2, "price": 20, "name": "২ দিন"},
    "7d": {"days": 7, "price": 50, "name": "৭ দিন"},
    "15d": {"days": 15, "price": 90, "name": "১৫ দিন"},
    "1m": {"days": 30, "price": 150, "name": "১ মাস"},
    "2m": {"days": 60, "price": 280, "name": "২ মাস"}
}

async def check_fsub(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=FORCE_SUB_CHANNEL, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception:
        pass
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_name = user.first_name
    
    existing_user = users_collection.find_one({"user_id": user_id})
    if not existing_user:
        users_collection.insert_one({
            "user_id": user_id,
            "name": user_name,
            "is_premium": False,
            "expiry_date": None,
            "joined_date": datetime.utcnow()
        })
    
    is_subscribed = await check_fsub(user_id, context)
    if not is_subscribed:
        keyboard = [[InlineKeyboardButton("📢 চ্যানেলে জয়েন করুন", url=f"https://t.me/{FORCE_SUB_CHANNEL.replace('@', '')}")],
                    [InlineKeyboardButton("🔄 আবার চেক করুন", callback_data="check_sub")]]
        await update.message.reply_text(
            f"হ্যালো {user_name}! আমাদের বট ব্যবহার করতে হলে প্রথমে নিচের চ্যানেলে জয়েন করতে হবে।",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    status_text = "সাধারণ মেম্বার ❌"
    if existing_user and existing_user.get("is_premium"):
        expiry = existing_user.get("expiry_date")
        if expiry and expiry > datetime.utcnow():
            status_text = f"প্রিমিয়াম মেম্বার ✅ (মেয়াদ শেষ: {expiry.strftime('%d-%m-%Y')})"
        else:
            users_collection.update_one({"user_id": user_id}, {"$set": {"is_premium": False, "expiry_date": None}})

    caption = (
        f"হ্যালো {user_name}! আমাদের প্রিমিয়াম বট সার্ভিসে স্বাগতম। 🚀\n\n"
        f"👤 **আপনার স্ট্যাটাস:** {status_text}\n\n"
        f"📜 **নোট:** আমাদের প্রিমিয়াম চ্যানেলে যুক্ত হয়ে এক্সক্লুসিভ ফাইল ও ভিডিও উপভোগ করুন।"
    )
    
    keyboard = [
        [InlineKeyboardButton("💎 প্রিমিয়াম প্ল্যান কিনুন", callback_data="buy_plans")],
        [InlineKeyboardButton("❓ হেল্প", callback_data="help"),
         InlineKeyboardButton("➕ গ্রুপে অ্যাড করুন", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ]
    
    photo_url = "https://i.ibb.co/4gR9Z9y/sample.jpg"
    try:
        await update.message.reply_photo(photo=photo_url, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_sub":
        user_id = query.from_user.id
        if await check_fsub(user_id, context):
            await query.message.delete()
            await start(update, context)
        else:
            await query.answer("আপনি এখনো চ্যানেলে জয়েন করেননি!", show_alert=True)
            
    elif query.data == "buy_plans":
        plans_caption = "💳 **মেম্বারশিপ প্ল্যানসমূহ (পেমেন্ট পেজ):**\nআপনার পছন্দের প্ল্যান সিলেক্ট করুন:"
        plans_keyboard = [
            [InlineKeyboardButton("১ দিন - ৳10", callback_data="pay_1d"), InlineKeyboardButton("২ দিন - ৳20", callback_data="pay_2d")],
            [InlineKeyboardButton("৭ দিন - ৳50", callback_data="pay_7d"), InlineKeyboardButton("১৫ দিন - ৳90", callback_data="pay_15d")],
            [InlineKeyboardButton("১ মাস - ৳150", callback_data="pay_1m"), InlineKeyboardButton("২ মাস - ৳280", callback_data="pay_2m")],
            [InlineKeyboardButton("🔙 ফিরে যান", callback_data="back_home")]
        ]
        try:
            await query.message.edit_media(media=InputMediaPhoto(media="https://i.ibb.co/4gR9Z9y/plans.jpg", caption=plans_caption, parse_mode="Markdown"), reply_markup=InlineKeyboardMarkup(plans_keyboard))
        except Exception:
            await query.edit_message_text(text=plans_caption, reply_markup=InlineKeyboardMarkup(plans_keyboard), parse_Mode="Markdown")

    elif query.data.startswith("pay_"):
        plan_key = query.data.split("_")[1]
        if plan_key in PLAN_PRICES:
            plan = PLAN_PRICES[plan_key]
            user_id = query.from_user.id
            
            expiry_date = datetime.utcnow() + timedelta(days=plan['days'])
            users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"is_premium": True, "expiry_date": expiry_date}}
            )

            payment_url = create_gateway_payment(user_id, plan['price'], plan['name'])
            
            pay_keyboard = [
                [InlineKeyboardButton("💳 পেমেন্ট করুন", url=payment_url)],
                [InlineKeyboardButton("🔙 ফিরে যান", callback_data="buy_plans")]
            ]
            await query.message.edit_caption(
                caption=f"📦 **প্ল্যান:** {plan['name']}\n💵 **মূল্য:** ৳{plan['price']}\n\nনিচের লিংকে ক্লিক করে পেমেন্ট সম্পন্ন করুন:",
                reply_markup=InlineKeyboardMarkup(pay_keyboard)
            )

    elif query.data == "back_home":
        await query.message.delete()
        await start(update, context)

def create_gateway_payment(user_id, amount, plan_name):
    api_endpoint = "https://api.yourpaymentgateway.com/v1/create-payment"
    payload = {
        "merchant_id": MERCHANT_ID,
        "api_key": API_KEY,
        "secret_key": SECRET_KEY,
        "amount": amount,
        "customer_id": str(user_id),
        "description": f"Premium Plan: {plan_name}"
    }
    try:
        response = requests.post(api_endpoint, json=payload, timeout=10)
        data = response.json()
        if response.status_code == 200 and "payment_url" in data:
            return data["payment_url"]
    except Exception as e:
        logging.error(f"Payment API Error: {e}")
        
    return f"https://yourpaymentgateway.com/pay?amount={amount}&user={user_id}"

def main():
    if not TOKEN:
        print("Error: BOT_TOKEN is missing!")
        return

    # পাইথন ৩.১৪ ইভেন্ট লুপ ফিক্স
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("Database connected and Telegram Bot is running successfully...")
    application.run_polling()

if __name__ == '__main__':
    main()
    
