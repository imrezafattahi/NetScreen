# NetScreen

سامانهٔ سبک پایش و عیب‌یابی شبکه با Python، FastAPI، SQLite، Docker و داشبورد فارسی/انگلیسی.

## قابلیت‌ها

پایش واقعی Ping با جایگزین TCP، بررسی HTTP/HTTPS، تحلیل DNS، ذخیرهٔ تاریخچه، هشدار تغییر وضعیت، داشبورد responsive، تغییر زبان و جهت RTL/LTR، اجرای Docker و تنظیم اختیاری تلگرام.

## اجرا

```bash
docker compose up -d
```

داشبورد در `http://localhost:8000`، مستندات API در `/api/docs` و سلامت سرویس در `/api/health` در دسترس است.

برای اجرای محلی:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --app-dir backend --reload
```

## مجوز

MIT
