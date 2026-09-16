# KIMMIZO MAC COMPLETE BUNDLE

โฟลเดอร์นี้เก็บ skill “คิม” เลขาผู้ช่วยผู้หญิงสำหรับ Codex บน Mac Apple Silicon

`✦ Auto` และ `athena-auto` ถูกเลิกใช้ใน bundle นี้ เพราะบัญชี ChatGPT ปฏิเสธโมเดลที่ไม่ใช่โมเดลทางการของ Codex. ให้เลือกโมเดลที่ Codex แสดงในเมนู Model เท่านั้น

## สิ่งที่อยู่ในโฟลเดอร์

- `skills/kimmizo/SKILL.md` — บุคลิกคิมผู้หญิงสำหรับติดตั้งเป็น Codex skill
- `uninstall.sh` — ถอน legacy Kimmizo Auto runtime หากเคยติดตั้งไว้
- `START_PROMPT_MAC.txt` — prompt เดียวสำหรับวางในแชท Codex บน Mac
- `STEP_BY_STEP_MAC.md` — วิธีเพิ่มโฟลเดอร์เข้า Codex และติดตั้งทีละขั้น
- `VERIFY_ON_MAC.md` — checklist หลังปิดและเปิด Codex ใหม่
- `bin/darwin-arm64/kimmizo-auto` — ไบนารี native สำหรับ Apple Silicon
- `kimmizo-auto-macos/` — source code และ policy ที่ตรวจด้วย SHA-256
- `BUNDLE-MANIFEST.sha256` — hash ของไฟล์ที่แจกทั้งหมด
- `BUILD-RECEIPT.json` — หลักฐานการ build บน Windows และขอบเขตที่ยังต้องตรวจบน Mac

## ติดตั้ง skill คิม

สมมติวางโฟลเดอร์ไว้ที่ `~/Desktop/Codex/KIMMIZO_MAC_COMPLETE_BUNDLE`:

```zsh
mkdir -p ~/.codex/skills
cp -R skills/kimmizo ~/.codex/skills/kimmizo
```

กด `Command-Q` เพื่อปิด Codex ให้หมด แล้วเปิดใหม่ จากนั้นเรียก “คิม” ในแชท และเลือกเฉพาะโมเดลทางการจากเมนู Model

ถ้าต้องการให้ Codex ทำขั้นตอนให้ทั้งหมด ให้นำโฟลเดอร์นี้เข้าเป็น Project แล้ววางข้อความจาก `START_PROMPT_MAC.txt` ในแชท

## ข้อกำหนด

- macOS บน Apple Silicon (`arm64`)
- ติดตั้ง Codex Desktop ไว้แล้ว
- ใช้งานบัญชี Codex เดิมของเครื่อง ไม่ต้องคัดลอกบัญชี ประวัติ หรือข้อมูลลับจากเครื่องอื่น
- ไม่ต้องติดตั้ง Homebrew, Go, Python, Node, .NET หรือ Xcode
- ไม่ใช้ `sudo`

## ถอน legacy Kimmizo Auto

```zsh
cd ~/Desktop/Codex/KIMMIZO_MAC_COMPLETE_BUNDLE
./uninstall.sh
```

ตัวถอนจะลบเฉพาะ installation root และ LaunchAgent ที่ผ่านการตรวจ ownership และคืน `previousCodexCliPath` เฉพาะเมื่อค่าปัจจุบันยังชี้มาที่ Kimmizo

## ขอบเขตการยืนยัน

ไบนารีนี้ cross-build และผ่าน unit/integration tests บน build host แล้ว แต่การขึ้น `✦ Auto` ใน UI ต้องยืนยันบน Mac หลังติดตั้งและเปิด Codex ใหม่ตาม `VERIFY_ON_MAC.md`

ดูการตั้งค่า Codex ทางการได้จาก [OpenAI Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)

## เหตุผลที่เลิกใช้ `✦ Auto`

แม้ UI สามารถแสดงชื่อ `✦ Auto` ได้ แต่เมื่อเริ่ม task Codex แจ้งว่า `athena-auto` ไม่รองรับกับบัญชี ChatGPT. นี่เป็นการตรวจฝั่งบริการ จึงไม่สามารถแก้ด้วย launcher, catalog หรือ config ในเครื่องได้. Bundle จึงเปลี่ยนเป็น skill คิมที่ทำงานร่วมกับโมเดลทางการได้จริง
