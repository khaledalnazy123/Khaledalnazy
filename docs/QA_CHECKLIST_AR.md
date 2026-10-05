# قبول MovieVault على Windows — قبل الاعتماد (الإصدار في `VERSION`)

**تحذير:** هذه قائمة تنفيذ يدوية، ليست اختبارات نجحت تلقائيًا. نفّذها على بيانات تجريبية أو نسخة مستقلة مع Backup.

- [ ] Python 3.12 x64؛ ffprobe.exe، وffmpeg.exe لميزة الغلاف الاختياري؛ WebView2؛ اختبر فتح النافذة وتكبيرها وتصغيرها وتحريكها 20 مرة دون تعليق.
- [ ] ثبّت v2 في مسار مستقل عن v1؛ أكد أن أيقونة v1 وقاعدة بيانات v1 ما زالت تعمل بعد تشغيل v2.
- [ ] خذ نسخة Backup من v1 على قرص آخر. داخل v2 افتح Settings > Import Previous Library، اختار مجلد v1 على Desktop، واضغط Preview. قارن أعداد Movies/Subtitles/IMDb/Roots.
- [ ] اختبر Auto-detect، والاختيار المباشر لـ `movievault.sqlite`، واستيراد Backup ZIP، وحالة ZIP فاسد (يُرفض). لا تُحذف أي ملفات من v1.
- [ ] اضغط Import وأعد تشغيل v2. تحقق من ظهور الأفلام وأسمائها الأصلية وتعديلاتك ومكتبة IMDb والترجمات والبوسترات اليدوية. أعد حساب الأعداد. تحقق من أن v1 بقيت كما كانت.
- [ ] أدخل TMDb Read Token محليًا مرة أخرى (لا ترفعه في أي Log)، وتحقق من Test & Save. Gemini اختياري وله مفتاح API مستقل عن اشتراك التطبيق.
- [ ] جرّب فحص فولدر فيلم وترجمتين (`Arabic` و`English`)، وتعديل اللغة والمصدر والجودة والترجمة، Apply Changes، ثم Rescan. يجب بقاء التعديل اليدوي.
- [ ] جرّب بحث Action فقط ثم Action+1080p ثم Action+Arabic+OSN، وتأكد أن Arabic+Netflix لا يطابق الفيلم إذا Netflix هي ترجمة English فقط.
- [ ] اختر Preferred Subtitle = OSN ثم شغل VLC/mpv وتأكد من عدم تغيير اسم الفيلم أو الترجمة الأصلية. غيّر الاختيار إلى Netflix ثم Ask Every Time.
- [ ] جرّب Find Poster Online مع TMDb، تغيير بوستر يدوي وLock، ثم Generate Custom Poster مع ffmpeg.exe. لا يُكتب فوق بوستر موجود دون إجراء صريح.
- [ ] جرّب Smart Update All بأوضاع Quick وMetadata وPosters وFull؛ جرّب Cancel Job، تحقق من تقدم العملية ومن حفظ التعديلات اليدوية.
- [ ] جرّب Dark وSoft Light وMidnight، ونسخ اسم الفيلم، وفتح Edit Movie Metadata وإغلاقه بالضغط خارج النافذة؛ يجب الرجوع إلى تفاصيل الفيلم.
- [ ] فصل الهارد الخارجي = Offline وليس حذف سجل الأفلام؛ حذف فيلم على هارد متصل بعد Scan = Missing مع بقاء الاسم الأصلي.
- [ ] Settings → Diagnostic Center → Export ZIP. افتح الملف وتأكد أنه لا يحتوي على توكنات TMDb/Gemini ولا قاعدة SQLite الأصلية ولا مساراتك الحساسة.
- [ ] اختبر Windows Portable ZIP وSetup.exe بعد بنائهما على Windows؛ نظافة التثبيت، الترقية من RC إلى إصدار تالٍ، الاحتفاظ بالبيانات بعد Uninstall، وعدم استبدال v1.
- [ ] تحقق أن أسماء Portable ZIP وSetup.exe، والنسخة داخل الواجهة وخصائص EXE، كلها تطابق ملف `VERSION`، وأن `release-manifest.json` ينجح عند إعادة فحصه.
- [ ] افحص `MovieVault.spdx.json` و`external-binaries.json` وتأكد من ظهور ffprobe/ffmpeg الصحيحين وبصمات SHA-256. لا توزع أي ملف مصدره غير موثوق.
- [ ] للبناء الموقّع: تحقق من Authenticode والتوقيت على MovieVault.exe وSetup.exe. للبناء غير الموقّع: تأكد أن `release-metadata.json` يذكر `UNSIGNED` بوضوح.
