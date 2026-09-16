# KIMMIZO MAC COMPLETE BUNDLE

ชุดติดตั้งผู้ช่วยภาษาไทยและ `✦ Auto` สำหรับ Codex Desktop บน Mac Apple Silicon

`✦ Auto` เป็น local UI preset ไม่ใช่โมเดลของบริการ เมื่อผู้ใช้เลือก preset นี้ runtime จะอ่าน model catalog ที่ Codex ส่งมา เลือกเฉพาะ model/effort ที่มีอยู่จริง แล้วแทนค่าเป็นโมเดลทางการก่อนส่ง request เข้า real Codex ทุกครั้ง Outbound guard จะหยุด request หากยังมี virtual slug เหลืออยู่

## ติดตั้ง

```zsh
chmod +x install.sh status.sh uninstall.sh name.sh
./install.sh
./status.sh
```

Installer จะไม่ถามและไม่ตั้งชื่อผู้ช่วย หลัง verification ผ่านแล้วจึงตั้งชื่อจากคำตอบของผู้ใช้:

```zsh
./name.sh "ชื่อที่ผู้ใช้ตอบ"
```

จากนั้นปิด Codex ด้วย `Command-Q` แล้วเปิดใหม่

## สิ่งที่ติดตั้ง

- `skills/kimmizo/SKILL.md` — policy บุคลิกภาษาไทยแบบยังไม่ตั้งชื่อ
- `~/.kimmizo-secretary/auto` — runtime, verified policy, voice policy และ state ที่ไม่เก็บ prompt
- `~/Library/LaunchAgents/com.kimmizo.kimmizo-auto.plist` — เปิด `CODEX_CLI_PATH` สำหรับ Codex Desktop
- `✦ Auto` — local preset ที่ route ไปยังโมเดลทางการจาก catalog

## ความปลอดภัย

- ไม่อ่านหรือคัดลอก token, credentials, private keys, password, connection string หรือ `.env`
- ไม่แก้ `~/.codex/config.toml`
- ไม่ส่ง `athena-auto` ไปยัง real Codex หรือบริการ OpenAI
- เก็บเฉพาะ thread ID, route ล่าสุด และสถานะ Auto; ไม่เก็บ prompt
- policy และ voice policy ตรวจ SHA-256 ก่อนใช้งาน
- installer และ uninstaller ตรวจ ownership receipt ก่อนแก้ installation root

## ข้อกำหนด

- macOS Apple Silicon (`arm64`)
- Codex Desktop ติดตั้งและเข้าสู่ระบบแล้ว
- ไม่ต้องติดตั้ง Homebrew, Go, Python, Node, .NET หรือ Xcode เพื่อใช้งาน bundle
- ไม่ใช้ `sudo`

## ตรวจสอบและถอนการติดตั้ง

```zsh
./status.sh
./uninstall.sh
```

`status.sh` ต้องรายงาน `status: ready`, `outboundModelGuard: true`, policy/voice verified, real CLI executable และ `✦ Auto` อยู่ใน local installed catalog
