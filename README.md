# DyReXR — تشغيل يوتيوب وإنستقرام وفيسبوك

## اللي صار
- `backend/` سيرفر Python (FastAPI + yt-dlp) يرد بنفس شكل JSON اللي كود `index.html`
  يتوقعه من Cobalt (`status: success/picker` + `url`)، فما احتجت أغيّر منطق الفرونت إند.
- `index.html` انعدّل بس بمكان `COBALT_ENDPOINT` وتسميات الأزرار — TikTok وX ما تغيّروا.
- `manifest.json` و `sw.js` كما هم، ما لهم علاقة بالمشكلة.

## 1) تشغيل السيرفر محليًا (تجربة سريعة)
```bash
cd backend
pip install -r requirements.txt
# لازم ffmpeg مثبت على جهازك (لدمج الفيديو+الصوت وتحويل MP3)
BASE_URL="http://localhost:8000" uvicorn main:app --host 0.0.0.0 --port 8000
```
جرّب: `http://localhost:8000/health` لازم يرجع `{"ok": true}`.

## 2) نشر السيرفر (حتى يوصله تطبيقك من الجوال)
أسهل خيارين لأن فيهم Docker + تخزين مؤقت كافي:

### Render.com
1. ارفع مجلد `backend/` إلى مستودع GitHub.
2. New → Web Service → اختر المستودع → Environment: **Docker**.
3. أضف Environment Variable: `BASE_URL = https://اسم-خدمتك.onrender.com`
   (خله بدون `/` بالنهاية).
4. (اختياري) أضف `API_KEY` بأي قيمة سرية لحماية السيرفر من الاستخدام العشوائي.
5. بعد النشر، Endpoint النهائي يصير: `https://اسم-خدمتك.onrender.com/api`

### Railway.app
نفس الخطوات: New Project → Deploy from GitHub → يكتشف الـ Dockerfile تلقائيًا →
أضف نفس متغيرات البيئة (`BASE_URL`, `API_KEY`) من تبويب Variables.

### أو VPS خاص بك (DigitalOcean / Hetzner إلخ)
```bash
docker build -t dyrexr-backend .
docker run -d -p 8000:8000 \
  -e BASE_URL="https://your-domain.com" \
  -e API_KEY="ضع-مفتاح-سري-هنا" \
  --name dyrexr-backend dyrexr-backend
```
وحط عليه Nginx/Caddy كـ reverse proxy مع شهادة SSL (HTTPS ضروري لأن الفرونت إند
غالبًا يفتح كـ PWA HTTPS ولن يقبل استدعاء رابط http عادي).

## 3) ربط الفرونت إند
افتح `index.html` وعدّل هذين السطرين داخل `CONFIG`:
```js
COBALT_ENDPOINT: "https://اسم-خدمتك.onrender.com/api",
API_KEY: "ضع-نفس-المفتاح-إذا-فعّلته"
```
ثم انشر `index.html` مع `manifest.json` و `sw.js` كما هي (رفعهم لنفس مكان الاستضافة الحالي).

## ملاحظات مهمة
- **الروابط المؤقتة**: السيرفر يحمّل الملف على نفسه أولًا ثم يعطي الفرونت إند رابط
  `/files/...` مؤقت (يُحذف تلقائيًا بعد نصف ساعة أو بعد أول تحميل). هذا أفضل بكثير
  من إرجاع رابط يوتيوب المباشر لأنه غالبًا مربوط بـ IP السيرفر ويفشل لو المستخدم
  فتحه من جواله مباشرة.
- **المساحة/الاستضافة المجانية**: يوتيوب أحيانًا يطلب تحقق إضافي من سيرفرات
  Render/Railway المجانية (كثرة الطلبات من نفس نطاق IP). إذا صار عندك أخطاء
  متكررة من نوع "Sign in to confirm you're not a bot"، الحل الشائع هو تمرير
  ملف كوكيز متصفح مسجّل دخول إلى yt-dlp عبر خيار `cookiefile`، أو استخدام VPS
  بدل الاستضافات المجانية المشتركة.
- **حقوق النشر والشروط**: هذا الإعداد لتحميل شخصي لمحتوى تملكه أو له ترخيص
  بالتحميل. تحميل محتوى محمي بدون إذن قد يخالف شروط استخدام يوتيوب/إنستقرام
  وقوانين حقوق النشر في بعض الدول — الاستخدام مسؤوليتك أنت.
- TikTok (TikWM) وX (VXTwitter) لم يتغيّر فيهم شيء ويستمرون بالعمل كما هم.
