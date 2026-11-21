# Daily Horror Story Bot (V8)

প্রতিদিন দুপুর ২টো ও রাত ৮টায় একটা করে নতুন বাংলা ভূতের গল্প তৈরি হয়। ভিডিও, Reel, Short, Podcast ও ওয়েবসাইট সবই নিজে থেকে তৈরি ও প্রকাশ হয়। পুরো কাজ GitHub Actions-এ চলে, তাই আপনার PC বন্ধ থাকলেও কাজ থামে না। এতে কোনো paid API, paid runner বা billing ব্যবহার হয় না (ZERO_COST)।

## কীভাবে চলে

1. cron-job.org প্রতিদিন রাত ২টো, সকাল ১০টা, দুপুর ২টো ও রাত ৮টার আগে `horror-story.yml` চালু করে। cron-job.org না চালালে GitHub-এর নিজের backup ঘড়ি ৭৫ মিনিট পরে চালু করে। একই সময়ের গল্প কখনও দুবার যায় না।
2. **বিষয় বাছাই:** Telegram-এ আপনাকে কিছু পাঠাতে হয় না। bot নিজেই বিষয় খোঁজে (AUTO_DISCOVER)। উৎস: Google News, Google Trends, Wikipedia, YouTube ট্রেন্ড আর Gemini + Google Search। এরপর বিষয়গুলোকে স্কোর দেয়, আগে ব্যবহার হওয়া বিষয় বাদ দেয়, আর উৎস-পাতা নিজে খুলে মিলিয়ে দেখে। প্রতিটি গল্পে নিচের তিনটির একটি লেবেল থাকে:
   - **সত্য ঘটনা অবলম্বনে:** অন্তত ২টি আলাদা উৎস-পাতা মিলিয়ে দেখা হয়েছে।
   - **ঘটনা থেকে অনুপ্রাণিত কাল্পনিক কাহিনি:** ১টি উৎস-পাতা মিলিয়ে দেখা হয়েছে।
   - **সম্পূর্ণ কাল্পনিক গল্প:** শুধু ট্রেন্ডিং বিষয় থেকে নেওয়া, কোনো সত্য-দাবি নেই।
3. **লেখা:** গল্প লেখে Gemini। এই ধাপে আগের সব নিয়ম, সিরিজ ও বিশেষ পর্ব আগের মতোই থাকে। `assets/`-এর প্রতিটা নমুনা গল্পের জন্য আলাদা একজন "সহকারী" আছে। গল্পের বিষয় দেখে যে নমুনা সবচেয়ে মানায়, তার ধাঁচ ব্যবহার হয়।
4. **কণ্ঠ:** প্রথমে Gemini TTS (ফ্রি key) ব্যবহার হয়। সেটা শেষ হলে Chirp, তারপর Parler বা Edge।
5. **ভিডিও:** Cloudflare-এর ছবি, 2.5D animation, শব্দ, subtitle আর thumbnail মিলিয়ে তৈরি হয়।
6. **প্রকাশ:** YouTube (ভিডিও, Short, playlist, podcast), Facebook (ভিডিও, Reel, Story), Instagram Reel (সংযুক্ত থাকলে), Podcast RSS (Spotify ও Apple Podcasts এটা নিজেরা পড়ে নেয়), Telegram চ্যানেল আর ওয়েবসাইট।

## Telegram কমান্ড

উত্তর আসে প্রায় ১৫ মিনিটের মধ্যে (`telegram-poll.yml`)। শুধু আপনার নিজের chat (`TELEGRAM_CHAT_ID`) থেকে পাঠানো কমান্ড মানা হয়।

| কমান্ড | কাজ |
| --- | --- |
| অবস্থা, /status | সব খবর |
| বন্ধ, বন্ধ ভূত ৩ দিন, চালু | ভিডিও বন্ধ বা চালু |
| বাদ ভূত ১ | লাইনের গল্প বাদ (আগের মতোই) |
| ১ বদলাও, ২ বদলাও | আজকের গল্প বদলাও (আগের মতোই) |
| ধাঁচ (অডিওর caption-এ) | নতুন নমুনা গল্প |
| ধাঁচ আবার শেখো | প্রতিটা নমুনার ধাঁচ নতুন করে তৈরি |
| ধাঁচ মুছে দাও | সব নমুনা মুছে ফেলো |
| আমার গলা মুছে দাও | আপনার কণ্ঠের clip মুছে ফেলো |
| /autodiscover_on, /autodiscover_off | bot নিজে বিষয় খুঁজবে কি না |
| /discover_now | এখনই বিষয় খুঁজে তালিকা পাঠাও |
| /topic_mode | বিষয় বাছাইয়ের মোড: AUTO_DISCOVER, TRUE_INCIDENT_PRIORITY, TRENDING_TOPIC_PRIORITY, USER_SUPPLIED বা MIXED |
| /topic বিষয় | আপনার দেওয়া বিষয় (ঐচ্ছিক) |
| /topic_queue | লাইনে কোন কোন বিষয় আছে |
| /research_sources | শেষ গল্পের উৎস |
| /podcast_status, /rss_status, /spotify_status, /apple_podcasts_status | Podcast-এর যাচাই করা অবস্থা |
| /destinations, /calendar | কোথায় প্রকাশ হয়, আর কখন |
| /autopublish_on/off, /youtube_on/off, /facebook_on/off, /podcast_on/off | প্রকাশের সুইচ |
| /retry_publish | যেখানে প্রকাশ হয়নি, শুধু সেখানে আবার চেষ্টা |
| /cancel_job | চলমান কাজ থামাও |
| /help | সব কমান্ডের তালিকা |

সাধারণ বাংলায় লিখলেও bot বোঝে। যেমন: "নিজে সত্য ঘটনা খুঁজে গল্প বানাও", "ট্রেন্ডিং হরর বিষয় খুঁজে তৈরি করো", "আজকের গল্প সব প্ল্যাটফর্মে প্রকাশ করো", "Spotify আর Apple Podcasts-এর অবস্থা দেখাও"।

## সুইচ (GitHub → Settings → Secrets and variables → Actions → Variables)

এখানে কিছু না লিখলে নিরাপদ ডিফল্ট মান ব্যবহার হয়।

| Variable | ডিফল্ট | অর্থ |
| --- | --- | --- |
| `ZERO_COST_MODE` | 1 | কোনো paid API ডাকা যাবে না (`zerocost.py`) |
| `CHIRP_APPROVED` | 1 | Gemini-র কণ্ঠ শেষ হলে Chirp ব্যবহার হবে (মাসিক সীমা `CHIRP_MONTH_CAP`) |
| `AUTO_DISCOVER` | 1 | bot নিজে বিষয় খুঁজবে |
| `TOPIC_MODE` | AUTO_DISCOVER | বিষয় বাছাইয়ের মোড |
| `BACKUP_CLOCK` | 1 | GitHub-এর backup ঘড়ি চালু থাকবে |
| `YT_TREND_API` | 1 | YouTube ট্রেন্ড আসবে অফিসিয়াল API থেকে (দিনে সর্বোচ্চ ৩টি খোঁজ) |
| `APPLE_PODCAST_ID`, `SPOTIFY_SHOW_ID` | — | Podcast যাচাইয়ের জন্য (ঐচ্ছিক) |
| `FACE_ANIM` | 0 | 1 দিলে মুখের পলক ও ঠোঁট নড়া দেখা যাবে |

## গোপনীয়তা

- সব key ও token শুধু GitHub Secrets-এ থাকে। কোডে বা repo-তে কোনো secret নেই।
- আপনার কণ্ঠের clip আর Telegram-এ পাঠানো ধাঁচের অডিও public repo-তে রাখা হয় না। শুধু Telegram-এর id রাখা থাকে।
- গবেষণার নথি শুধু আপনার Telegram-এ যায়। repo-তে থাকে শুধু উৎসের লিংক আর স্কোর।
- Podcast RSS public, এটা ফিডের স্বভাব। তাই `PODCAST_EMAIL`-এ ব্যক্তিগত নয়, আলাদা একটা ইমেইল দিন।

## পরীক্ষা

```
MOCK=1 python -m pytest -q tests                # নেটওয়ার্ক ছাড়াই, কিছু প্রকাশ হয় না
MOCK=1 HORROR_MINUTES=1 python main.py          # পুরো pipeline-এর অফলাইন মহড়া
```

`tests/feature_snapshot.json`-এ V8-এর আগের প্রতিটা function, সেটিং, secret ও সংরক্ষিত ফাইলের তালিকা আছে। এর কোনোটা হারিয়ে গেলে test ব্যর্থ হবে।
