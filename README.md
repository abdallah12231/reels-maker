# 🎬 Reels Maker

حوّل أي فيديو لريلز جاهزة بالذكاء الاصطناعي

## الملفات
- `main.py` - السيرفر الرئيسي
- `requirements.txt` - المكتبات المطلوبة
- `Dockerfile` - إعدادات Railway
- `index.html` - واجهة المستخدم

## طريقة الرفع على Railway

1. ارفع كل الملفات على GitHub
2. في Railway اختار "Deploy from GitHub"
3. أضف متغير البيئة: `ANTHROPIC_API_KEY`
4. انتظر الـ Deploy ينتهي
5. افتح `index.html` في المتصفح

## متطلبات
- Python 3.11+
- FFmpeg (متضمن في Dockerfile)
- Anthropic API Key
