# MovieVault v2 — SOURCE PREVIEW (الإصدار الدقيق في `VERSION`)

هذه نسخة تطويرية قابلة للتجربة من مكتبة أفلام Windows. **ليست Setup.exe جاهزًا أو إصدارًا مستقرًا مختبرًا على Windows**. لا تستوردها فوق إصدار v1 ولا تحذف مجلدات بيانات v1. تفضّل دائمًا أخذ Backup قبل الانتقال.

## أهم إضافة: Import Previous Library (v1 → v2)

- v1 يخزن بياناتك عادةً في `%LOCALAPPDATA%\MovieVault\movievault.sqlite`، بينما v2 يستخدم ملفًا منفصلًا في `%LOCALAPPDATA%\MovieVault\v2\movievault.sqlite`.
- عند أول تشغيل يظهر إعلان Import Previous Library. أو: Settings → Import Previous Library.
- يمكنك اختيار **فولدر البرنامج القديم MovieVault_v1**، أو فولدر بيانات النسخة القديمة، أو ملف `movievault.sqlite` نفسه، أو نسخة Backup ZIP رسمية من v1. لو اخترت فولدر كود v1 فقط، يحاول البرنامج اكتشاف البيانات الحقيقية من `%LOCALAPPDATA%\MovieVault`.
- اضغط Auto-detect أو Browse ثم **Preview Data**. ستظهر أعداد الأفلام، والترجمات، وسجلات IMDb، والفولدرات والبوسترات القابلة للنقل قبل اتخاذ القرار.
- اضغط Import Previewed Data ثم أغلق v2 وأعد تشغيله. الاستيراد يتم من Snapshot، لا يكتب في v1، ويمنع استبدال مكتبة v2 لو أصبحت تحتوي على بيانات.
- يُستورد فهرس IMDb والأسماء الأصلية ومصادر الترجمات والتعديلات والملاحظات والصور المحلية/اليدوية الصالحة. **لا تنقل رموز TMDb/Gemini السرية ولا كاش TMDb المؤقت**؛ أدخلها مرة أخرى محليًا عند الحاجة.
- إذا سبق لك إدخال أفلام في v2، أنشئ Backup منفصلًا ولا تحاول الكتابة فوقها. لم يُنفذ دمج مكتبتين عامتين عشوائيًا في النسخة الحالية.

## تجربة البرنامج من الكود على Windows

1. احتفظ بفولدر MovieVault_v1 القديم كما هو، واعمل Create Backup منه وانسخه على قرص آخر.
2. فك ضغط حزمة v2 في مجلد جديد مختلف عن v1 (مثل `Desktop\MovieVault_v2`). لا تعمل Replace فوق ملفات v1.
3. استخدم Python **3.12 64-bit** (الإصدار الذي سبق وثبّتّه يعمل بجانب 3.14).
4. من CMD داخل فولدر v2 نفّذ:

   `py -3.12 -m pip install -r requirements-windows.txt`

5. ضع `ffprobe.exe` الموثوق داخل `vendor` لاستخراج المواصفات الفنية. يُفضّل وضع `ffmpeg.exe` بجانبه لو أردت Generate Custom Poster.
6. شغّل: `py -3.12 MovieVault.pyw`. لو حدثت مشكلة في محرك نافذة Windows جرب `py -3.12 dev.py --browser` للتشخيص؛ هذا يفتح نفس قاعدة v2 ولا يعيدك إلى v1.
7. Settings → Import Previous Library → Auto-detect Previous Library → Preview Data → Import → Restart، أو اختر فولدر v1 بنفسك.
8. جرّب أولًا على فيلم صغير وترجمتين خارجيتين قبل فحص مكتبتك الكبيرة.

**مهم:** Windows WebView2 Runtime قد يكون مطلوبًا للنافذة المدمجة. المفاتيح تُحفظ لحساب Windows باستخدام DPAPI، ولا تشارك توكناتك داخل المحادثات أو Diagnostic ZIP.

## الوظائف الموجودة في النسخة الحالية

- قاعدة SQLite v2 مستقلة + استيراد اختياري من v1 (ملف/فولدر/Backup ZIP) ومعاينة قبل الاستيراد.
- فحص الفيديو والترجمة داخل نفس الفولدر، تحديث البيانات دون تغيير الاسم الأصلي، أرشفة Missing/Offline، FFprobe وView Full Info.
- كروت Genre/IMDb Rating عند توفره، ملخص عدة ترجمات، نسخ اسم الفيلم، فلاتر تراكمية اختيارية على الاسم والنوع والممثل والجودة والسنة واللغة ومصدر الترجمة والمترجم. يجمع شروط اللغة والمصدر على **نفس** صف الترجمة.
- تحديد لغة افتراضية للترجمات الخارجية غير المعروفة (Arabic)، وتعديل لغة ومصدر وجودة ومترجم كل ترجمة مع Apply Changes؛ تعديلات اللغة اليدوية تصمد أمام Rescan.
- Custom Subtitle Sources، Preferred Playback Subtitle (Auto / Ask / None / Selected)، تمرير ترجمة خارجية لـVLC أو mpv من دون إعادة تسمية ملفك الأصلي.
- TMDb/IMDb منفصلان: IMDb offline titles + IMDb official ratings file، وTMDb للبوسترات والممثلين والنبذة والتقييم الخاص به. Gemini اقتراح اختياري فقط بعد فشل المطابقة المعتادة ثم تحقق مستقل من TMDb.
- إدارة بوسترات: الموجودة محليًا أولًا، TMDb ثم Commons عند توفر تطابق/حقوق مناسبة، Custom Frame Poster مستقل باستخدام FFmpeg + Pillow، كاش TMDb منتهي الصلاحية وفق شروط المصدر.
- Dark/Light/Midnight (تجريبية)، Favorites وPersonal Rating في Edit، Smart Update All بأوضاع Quick/Metadata/Posters/Full، Cancel Job، Diagnostic ZIP بخصوصية محسّنة.

## حدود النسخة الحالية وميزات تحتاج اختبارًا إضافيًا

- **لم يتم بناء/تشغيل/اختبار Setup.exe داخل بيئة Windows الحالية**؛ ملف `MovieVault.iss` وسكربت `BUILD_WINDOWS.cmd` معدان ليُنفذا على Windows بعد فحصهما هناك.
- تكامل TMDb/Gemini الحقيقي مع حسابك وWindows DPAPI يتطلب اختبارًا محليًا على جهازك؛ الاختبارات المتاحة تستخدم محاكاة للطلبات ولا تحتوي على توكن حقيقي.
- VLC أو mpv مطلوب لو أردت فرض ترجمة محددة دون إعادة تسمية الملفات؛ المشغل الافتراضي قد لا يدعم هذا الخيار.
- لا نضمن التوفر الدائم لكل بوستر رسمي أو حق حفظه بشكل دائم؛ صور TMDb في كاش مؤقت طبقًا للشروط. الفيديو المحلي لا يُرفع.
- النسخة الحالية لا تضم واجهة نهائية لتجميع نسخ الفيلم المختلفة تحت كارت واحد، أو تقرير Duplicate Detector مستقل، أو سجل Recently Watched كامل؛ البيانات الإضافية والأساس الحالي يسمحان بالتوسع لاحقًا. لا ندعي اختبار هذه الوظائف أو تنفيذها بالكامل.
- لا يوجد وعد بانعدام كل الثغرات. راجع `docs/QA_REPORT.md` و`docs/KNOWN_LIMITATIONS.md`، وجرّب بعينة أولًا.

## بناء Windows Setup.exe (على جهاز Windows فقط)

1. ثبت Python 3.12 x64، وInno Setup 6، وffprobe.exe من توزيع FFmpeg موثوق مع الالتزام برخصته (وffmpeg.exe اختياري لميزة Custom Frame).
2. افتح CMD من فولدر المشروع وشغّل `BUILD_WINDOWS.cmd`.
3. السكربت يتحقق من `VERSION` ومن القفلين ذوي الإصدارات والبصمات الدقيقة، يجري اختبارات unittest، يبني EXE عبر PyInstaller، ثم يفحص محتوى الحزمة وينشئ Portable ZIP ومثبت Inno Setup داخل `release`.
4. للمراجعة اليدوية افتح `build_windows.ps1` و`MovieVault.iss`. يستخدم v2 معرف AppId ومسار تثبيت مختلفين عن v1: **لن يتعمد استبدال تثبيت v1**.
5. شغل قائمة QA على Windows قبل توزيع الملف أو وصفه بأنه Stable. يجب اختبار تثبيت v2، التحديث إلى إصدار v2 لاحق، أخذ Backup، فتح وإغلاق النافذة، وفصل الهارد أثناء Scan.
6. راجع `docs/RELEASE_ENGINEERING.md` لتحديث الأقفال، مصدر ffprobe/ffmpeg، SBOM، manifest، وإعداد توقيع Authenticode. لا توجد مفاتيح توقيع داخل المستودع، والبناء بلا إعداد خارجي يُعلَّم `UNSIGNED` بوضوح.

## ملفات مهمة

- `START_HERE.txt` خطوات البدء السريعة.
- `docs/MIGRATION_V1_TO_V2_AR.md` دليل مصوّر بالخطوات النصية والتحذيرات.
- `docs/QA_REPORT.md` نتائج الآلة وحدود التحقق.
- `docs/FEATURE_STATUS.md` منفذ/جزئي/مؤجل.
- `CODEX_REVIEW_INSTRUCTIONS.md` تعليمات مراجعة مستقبلية عند توافر حصتك؛ بدون مفاتيح خاصة.

> MovieVault برنامج فهرسة شخصي وليس خدمة للحصول على ملفات أفلام. التزم بحقوق المحتوى والصور وشروط TMDb وIMDb وGemini.

## اختبار أوتوماتيكي بنقرة واحدة

على Windows يمكنك تشغيل `RUN_AUTOMATED_QA.cmd`. سيشغّل اختبارات الوحدة والتكامل وفحص Syntax، ويضيف اختبار الواجهة البصري إذا كانت Playwright متاحة. النتيجة تُحفظ داخل `qa_reports` بصيغتي TXT وJSON. نجاح الاختبارات الآلية لا يغني عن قائمة اختبار Windows الفعلية المذكورة في `docs/QA_CHECKLIST_AR.md`.

لإضافة اختبار UI آلي اختياري، شغّل `INSTALL_QA_TOOLS.cmd` مرة واحدة (سينزل Playwright/Chromium للاختبار فقط)، ثم `RUN_AUTOMATED_QA.cmd`. هذا غير مطلوب لتشغيل MovieVault نفسه.
