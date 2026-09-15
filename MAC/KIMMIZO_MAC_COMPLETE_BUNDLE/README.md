# KIMMIZO MAC COMPLETE BUNDLE

โฟลเดอร์นี้เป็นแพ็กเกจอิสระสำหรับติดตั้ง “เลขาคิม” และโมเดลเสมือน `✦ Auto` บน Mac Apple Silicon

`✦ Auto` ไม่ใช่โมเดลทางการของ OpenAI แต่เป็นตัวเลือกในเครื่องที่เลือกโมเดลจริงและ reasoning effort จาก catalog ที่ Codex ส่งมาในขณะใช้งาน ตัว router จะไม่บันทึก prompt หรือ response ลงไฟล์สถานะ

## สิ่งที่อยู่ในโฟลเดอร์

- `install.sh` — ติดตั้งแบบ user-scoped พร้อม rollback
- `status.sh` — ตรวจ runtime, policy, voice, LaunchAgent และ `CODEX_CLI_PATH`
- `uninstall.sh` — ถอนการติดตั้งและคืนค่าเดิมเมื่อ Kimmizo ยังเป็นเจ้าของค่าอยู่
- `START_PROMPT_MAC.txt` — prompt เดียวสำหรับวางในแชท Codex บน Mac
- `STEP_BY_STEP_MAC.md` — วิธีเพิ่มโฟลเดอร์เข้า Codex และติดตั้งทีละขั้น
- `VERIFY_ON_MAC.md` — checklist หลังปิดและเปิด Codex ใหม่
- `bin/darwin-arm64/kimmizo-auto` — ไบนารี native สำหรับ Apple Silicon
- `kimmizo-auto-macos/` — source code และ policy ที่ตรวจด้วย SHA-256
- `BUNDLE-MANIFEST.sha256` — hash ของไฟล์ที่แจกทั้งหมด
- `BUILD-RECEIPT.json` — หลักฐานการ build บน Windows และขอบเขตที่ยังต้องตรวจบน Mac

## ติดตั้งเร็ว

สมมติวางโฟลเดอร์ไว้ที่ `~/Desktop/Codex/KIMMIZO_MAC_COMPLETE_BUNDLE`:

```zsh
cd ~/Desktop/Codex/KIMMIZO_MAC_COMPLETE_BUNDLE
chmod +x install.sh status.sh uninstall.sh
./install.sh
```

ตัวติดตั้งจะถามชื่อก่อนเริ่มงาน โดยค่าเริ่มต้นคือ “เลขาคิม” หรือระบุล่วงหน้าได้:

```zsh
./install.sh --name "ชื่อที่ต้องการ"
```

จากนั้นกด `Command-Q` เพื่อปิด Codex ให้หมด เปิดใหม่ แล้วเลือก `✦ Auto` ในเมนู Model ก่อนรัน:

```zsh
cd ~/Desktop/Codex/KIMMIZO_MAC_COMPLETE_BUNDLE
./status.sh
```

ถ้าต้องการให้ Codex ทำขั้นตอนให้ทั้งหมด ให้นำโฟลเดอร์นี้เข้าเป็น Project แล้ววางข้อความจาก `START_PROMPT_MAC.txt` ในแชท

## ข้อกำหนด

- macOS บน Apple Silicon (`arm64`)
- ติดตั้ง Codex Desktop ไว้แล้ว
- ใช้งานบัญชี Codex เดิมของเครื่อง ไม่ต้องคัดลอกบัญชี ประวัติ หรือข้อมูลลับจากเครื่องอื่น
- ไม่ต้องติดตั้ง Homebrew, Go, Python, Node, .NET หรือ Xcode
- ไม่ใช้ `sudo`

## ถ้าตัวติดตั้งหา Codex จริงไม่พบ

ค้นหาเฉพาะ executable ใน app bundle:

```zsh
find /Applications/Codex.app/Contents/Resources -type f \( -name codex -o -name codex-cli \) -perm -111 -print
```

แล้วระบุ absolute path ที่พบ เช่น:

```zsh
./install.sh --real-codex /Applications/Codex.app/Contents/Resources/codex
```

หาก `CODEX_CLI_PATH` ถูกเครื่องมืออื่นใช้อยู่ ตัวติดตั้งจะหยุดโดยไม่เขียนทับ ให้ตรวจและถอนตัวควบคุมเดิมก่อน ไม่ควร unset ค่าโดยไม่ทราบเจ้าของ

## ถอนการติดตั้ง

```zsh
cd ~/Desktop/Codex/KIMMIZO_MAC_COMPLETE_BUNDLE
./uninstall.sh
```

ตัวถอนจะลบเฉพาะ installation root และ LaunchAgent ที่ผ่านการตรวจ ownership และคืน `previousCodexCliPath` เฉพาะเมื่อค่าปัจจุบันยังชี้มาที่ Kimmizo

## ขอบเขตการยืนยัน

ไบนารีนี้ cross-build และผ่าน unit/integration tests บน build host แล้ว แต่การขึ้น `✦ Auto` ใน UI ต้องยืนยันบน Mac หลังติดตั้งและเปิด Codex ใหม่ตาม `VERIFY_ON_MAC.md`

ดูการตั้งค่า Codex ทางการได้จาก [OpenAI Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
