# الاختبار الأوتوماتيكي في MovieVault v2

- شغّل `RUN_AUTOMATED_QA.cmd` من Windows لتشغيل اختبارات الوحدة والتكامل وفحص Syntax.
- اختبار الواجهة البصري اختياري. لتفعيله مرة واحدة شغّل `INSTALL_QA_TOOLS.cmd`، ثم أعد تشغيل `RUN_AUTOMATED_QA.cmd`.
- النتائج تُحفظ محليًا داخل `qa_reports` بصيغتي TXT وJSON.
- لا يتم تضمين مفاتيح TMDb/Gemini أو قاعدة مكتبتك داخل تقارير QA.
- الاختبارات الآلية لا تستبدل اختبارات Windows الحقيقية لـWebView2/DPAPI/VLC/mpv/Setup.exe.
