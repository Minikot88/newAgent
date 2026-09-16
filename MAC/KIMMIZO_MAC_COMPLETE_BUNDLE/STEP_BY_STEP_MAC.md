# ติดตั้ง Kimmizo Auto บน Mac ทีละขั้น

1. เปิด Project ที่ root ของ `KIMMIZO_MAC_COMPLETE_BUNDLE`
2. ยืนยันระบบ:

   ```zsh
   uname -s
   uname -m
   basename "$PWD"
   ```

   ต้องได้ `Darwin`, `arm64` และ `KIMMIZO_MAC_COMPLETE_BUNDLE`

3. ตรวจ manifest และติดตั้ง:

   ```zsh
   /usr/bin/shasum -a 256 -c BUNDLE-MANIFEST.sha256
   chmod +x install.sh status.sh uninstall.sh name.sh
   ./install.sh
   ```

   Installer ไม่ถามชื่อและไม่แก้ `~/.codex/config.toml`

4. ตรวจสถานะด้วย `./status.sh`
5. ปิด Codex ด้วย `Command-Q` แล้วเปิดใหม่
6. เปิดเมนู Model และเลือก `✦ Auto`
7. เริ่มงานอ่านอย่างเดียวเพื่อทดสอบ routing แล้วรัน `./status.sh` อีกครั้ง
8. เมื่อทุกข้อผ่านแล้วจึงถามชื่อผู้ช่วย และนำคำตอบมาตั้งด้วย `./name.sh "ชื่อที่ผู้ใช้ตอบ"`
9. ปิดและเปิด Codex ใหม่หลังตั้งชื่อ

## หลักการทำงาน

- `✦ Auto` ปรากฏเฉพาะใน UI/local catalog
- `thread/start`, `thread/resume`, `thread/fork` และ `turn/start` ถูกแปลงเป็น official model ก่อนส่งต่อ
- request ที่ยังมี virtual model ใน model field จะถูกหยุดแบบ fail-closed
- `เริ่มงานใหม่:` เริ่มการประเมิน route ใหม่
- งาน Ultra ต้องได้รับข้อความอนุมัติแยกต่างหาก

## หากตรวจไม่ผ่าน

รัน `./status.sh` และแก้ตามบรรทัด `DEGRADED` ห้ามแก้ `CODEX_CLI_PATH` หรือ `~/.codex/config.toml` ด้วยตนเอง ให้รัน installer ซ้ำจาก bundle เดิมหลังตรวจ ownership receipt แล้ว
