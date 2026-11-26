# Daily Horror Story Bot — ফাইনাল জিরো-কনফিগ লাইভ ২.৫ডি কার্টুন প্যাকেজ

এই ZIP ফাইলটি Extract করলে ভেতরে কোনো অতিরিক্ত ফোল্ডার থাকবে না—সরাসরি আপনার GitHub রিপোজিটরির সঠিক ফোল্ডার কাঠামো অনুযায়ী ৭টি ফাইল পাবেন।

## আপনার `.yml` ফাইল বা কোনো Secret বদলাতে হবে না:
`main.py`-এর ভেতরেই সবকিছু স্বয়ংক্রিয়ভাবে সেট করে দেওয়া হয়েছে। আপনার `.github/workflows/horror-story.yml` ফাইলে `ANIM_MODE` যাই থাকুক (খালি বা `tvtoon`), বটটি নিজে থেকেই **Hybrid 2.5D Live Cartoon Engine** চালু করবে—তাই আপনার আসল ওয়ার্কফ্লো ফাইল ওভাররাইট করার কোনো ঝুঁকি নেই।

## যে ৭টি ফাইল রিপোজিটরিতে আপলোড/রিপ্লেস করবেন:
1. `main.py` -> রিপোজিটরির মূল (root) ফোল্ডারে পুরোনো `main.py` রিপ্লেস করুন।
2. `cartoon25d.py` -> রিপোজিটরির মূল (root) ফোল্ডারে রিপ্লেস/আপলোড করুন।
3. `tvtoon/scene.py` -> `tvtoon/` ফোল্ডারে রিপ্লেস করুন।
4. `tvtoon/studio.py` -> `tvtoon/` ফোল্ডারে রিপ্লেস করুন।
5. `docs/podcast.json` -> `docs/` ফোল্ডারে রিপ্লেস করুন।
6. `docs/podcast.xml` -> `docs/` ফোল্ডারে রিপ্লেস করুন।
7. `tests/test_cartoon25d.py` -> `tests/` ফোল্ডারে রিপ্লেস/আপলোড করুন।

## টেস্ট রান করার নিয়ম (পোস্ট না করে):
1. ওপরের ৭টি ফাইল রিপোজিটরিতে আপলোড করে Commit করুন।
2. আপনার Telegram বটে `/autopublish_off` পাঠান।
3. GitHub-এ গিয়ে **Actions -> Daily Horror Story -> Run workflow** চালান (`mode` ফাঁকা রেখে)।
4. রান শেষ হলে Summary পেজের নিচে `horror-video` artifact থেকে ভিডিও ডাউনলোড করে দেখুন; পছন্দ হলে Telegram-এ `/autopublish_on` পাঠিয়ে দিন।
