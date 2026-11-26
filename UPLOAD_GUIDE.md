# Daily Horror Story Bot — ফাইনাল ২.৫ডি ইলাস্ট্রেটেড কার্টুন ইঞ্জিন আপলোড গাইড

এই ZIP ফাইলটি Extract করলে ভেতরে কোনো অতিরিক্ত ফোল্ডার (যেমন final_pkg_v3) থাকবে না—সরাসরি আপনার GitHub রিপোজিটরির সঠিক ফোল্ডার কাঠামো অনুযায়ী ফাইলগুলো পাবেন।

## যে ৭টি ফাইল রিপোজিটরিতে আপলোড/রিপ্লেস করবেন:
1. `cartoon25d.py` -> রিপোজিটরির মূল (root) ফোল্ডারে নতুন ফাইল হিসেবে আপলোড করুন।
2. `main.py` -> রিপোজিটরির মূল (root) ফোল্ডারে পুরোনো `main.py` রিপ্লেস করুন।
3. `tvtoon/scene.py` -> `tvtoon/` ফোল্ডারে রিপ্লেস করুন।
4. `tvtoon/studio.py` -> `tvtoon/` ফোল্ডারে রিপ্লেস করুন।
5. `docs/podcast.json` -> `docs/` ফোল্ডারে রিপ্লেস করুন।
6. `docs/podcast.xml` -> `docs/` ফোল্ডারে রিপ্লেস করুন।
7. `tests/test_cartoon25d.py` -> `tests/` ফোল্ডারে আপলোড করুন।

## টেস্ট রান করার নিয়ম (পোস্ট না করে):
1. ফাইলগুলো আপলোড করে Commit করুন (কোনো Secret বা Workflow ফাইল বদলাতে হবে না)।
2. আপনার Telegram বটে `/autopublish_off` পাঠান।
3. GitHub-এ গিয়ে **Actions -> Daily Horror Story -> Run workflow** চালান (`mode` ফাঁকা রেখে)।
4. রান শেষ হলে `horror-video` artifact থেকে নতুন ২.৫ডি কার্টুন ভিডিও ডাউনলোড করে দেখুন।
5. ভিডিও পছন্দ হলে Telegram-এ `/autopublish_on` পাঠিয়ে দিন।
