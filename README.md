# My Gym bot

Toshkent sport zallari uchun Telegram AI-bot: til tanlash → tuman → zallar → savol-javob (Gemini, faqat jadvaldagi ma'lumotga tayanadi) → yozilish (lead) → zal egasiga xabar.

## 1. Tayyorgarlik (bir marta)

1. **Telegram bot**: @BotFather → `/newbot` → nomi `My Gym` → token oling.
2. **Gemini kaliti**: aistudio.google.com → *Get API key*.
3. **Firebase**: console.firebase.google.com → yangi loyiha → *Firestore Database* → *Create database* (production mode, istalgan region).
   *Project settings → Service accounts → Generate new private key* → JSON faylni `service-account.json` nomi bilan shu papkaga qo'ying.
4. **Google Sheets API ni yoqish**: console.cloud.google.com → yuqorida shu Firebase loyihasini tanlang → *APIs & Services → Library* → "Google Sheets API" → *Enable*.
5. **Jadval**: sheets.google.com da yangi jadval oching.
   - *File → Import → Upload* → `gyms_sample.csv` → *Insert new sheet(s)* → import qiling.
   - Varaq nomini aynan **Zallar** qilib o'zgartiring.
   - *Share* → `service-account.json` ichidagi `client_email` manzilini **Editor** qilib qo'shing.
   - Jadval havolasidagi ID ni oling: `docs.google.com/spreadsheets/d/`**`SHU_YERDA`**`/edit`
6. **Telegram ID** ingizni @userinfobot dan oling (yoki botga `/id` yozing).
7. `.env.example` ni `.env` ga nusxalab, hammasini to'ldiring.

## 2. Kompyuterda sinash

```
pip install -r requirements.txt
python main.py
```
Telegramda botingizga `/start` yozing.

## 3. Railway'ga joylash

1. Papkani GitHub'ga yuklang (`.env` va `service-account.json` yuklanmasin, `.gitignore` buni biladi).
2. railway.app → *New Project → Deploy from GitHub repo*.
3. *Variables* bo'limida `.env` dagi hamma qiymatni kiriting. `GOOGLE_CREDENTIALS_FILE` o'rniga `GOOGLE_CREDENTIALS_JSON` ga `service-account.json` ichidagi BUTUN matnni qo'ying.
4. Deploy tugagach loglarda `My Gym bot ishga tushdi` yozuvini ko'rasiz.

## 4. Zallarni boshqarish (jadval ustunlari)

| Ustun | Izoh |
|---|---|
| id | Noyob qisqa nom: g001, g002... |
| name | Zal nomi |
| district | Tuman nomi, aynan shunday yoziladi: Bektemir, Chilonzor, Mirobod, Mirzo Ulug'bek, Olmazor, Sergeli, Shayxontohur, Uchtepa, Yakkasaroy, Yangihayot, Yashnobod, Yunusobod |
| address | Manzil |
| lat, lon | Lokatsiya (Google Maps'da joyni bosib, koordinatani nusxalang: 41.2755, 69.2030) |
| phone, tg_username | Zal egasi/administratori kontakti (oldin undan ruxsat oling) |
| owner_tg_id | Egasining Telegram ID si (u botga `/start` bosgan bo'lishi kerak, ID ni `/id` buyrug'i beradi) |
| hours, prices, amenities, notes | Matnlar. Bot javoblarini FAQAT shu ma'lumotdan oladi |
| photos | Rasmlar: `|` bilan ajratilgan file_id lar yoki to'g'ridan-to'g'ri rasm havolalari |
| free_trial | `ha` bo'lsa "Bepul sinov" tugmasi chiqadi, `yo'q` bo'lsa chiqmaydi |
| active | `ha` / `yo'q` (yo'q bo'lsa zal botda ko'rinmaydi) |

**Rasm file_id olish:** super admin sifatida botga rasm yuboring, bot file_id ni qaytaradi. Uni `photos` ustuniga qo'ying.

Jadvaldagi o'zgarishlar botga taxminan 1 daqiqada o'tadi (`/reload` darhol yangilaydi).

## 5. Buyruqlar

- Hamma: `/start`, `/menu`, `/language`, `/cancel`, `/id`
- Zal egasi: `/mystats`, `/leads`
- Super admin: `/stats`, `/leads`, `/gyms`, `/reload`

Leadlar Firebase'ga va jadvalning **Leads** varag'iga yoziladi (varaq o'zi yaratiladi).
Instagram reklamasi havolasi: `https://t.me/<bot_username>?start=insta`. Manba `/stats` da ko'rinadi.

> Eslatma: namunadagi 4 ta zal to'qib chiqarilgan. Haqiqiy zallarni qo'shishdan oldin ularni jadvaldan o'chiring yoki `active` ni `yo'q` qiling.
