# ติดตั้งเลขาคิมบน Mac ทีละขั้น

## วิธี A — เพิ่มโฟลเดอร์เข้า Codex แล้วใช้ prompt เดียว

1. คัดลอกทั้งโฟลเดอร์ `KIMMIZO_MAC_COMPLETE_BUNDLE` ไปที่:

   ```text
   /Users/<ชื่อผู้ใช้>/Desktop/Codex/KIMMIZO_MAC_COMPLETE_BUNDLE
   ```

2. เปิด Codex บน Mac แล้วเลือกเพิ่ม Project/Folder
3. เลือกโฟลเดอร์ `KIMMIZO_MAC_COMPLETE_BUNDLE` ทั้งโฟลเดอร์ ไม่ใช่เลือกไฟล์ย่อย
4. เปิด task ใหม่ใน Project นี้
5. เปิด `START_PROMPT_MAC.txt`, คัดลอกข้อความทั้งหมด แล้ววางในแชท
6. อนุญาตเฉพาะคำสั่งที่ทำงานภายในโฟลเดอร์ bundle, `~/.kimmizo-secretary/auto` และ `~/Library/LaunchAgents/com.kimmizo.kimmizo-auto.plist`
7. รอผล `PASS` จาก `./status.sh`
8. กด `Command-Q` เพื่อปิด Codex ให้หมด แล้วเปิดใหม่
9. เปิดเมนู Model และเลือก `✦ Auto`
10. กลับมาที่ Project bundle แล้วตรวจตาม `VERIFY_ON_MAC.md`

## วิธี B — ติดตั้งเองใน Terminal

เปิด Terminal แล้วรัน:

```zsh
cd ~/Desktop/Codex/KIMMIZO_MAC_COMPLETE_BUNDLE
chmod +x install.sh status.sh uninstall.sh
./install.sh
```

ตัวติดตั้งจะถามชื่อก่อนเริ่มติดตั้ง หากต้องการกำหนดล่วงหน้าให้ใช้ `./install.sh --name "ชื่อที่ต้องการ"`

ผลสำเร็จควรมีบรรทัด:

```text
PASS: Kimmizo installed at /Users/<ชื่อผู้ใช้>/.kimmizo-secretary/auto
```

จากนั้นปิด Codex ด้วย `Command-Q`, เปิดใหม่ และรัน:

```zsh
cd ~/Desktop/Codex/KIMMIZO_MAC_COMPLETE_BUNDLE
./status.sh
```

## ถ้าหา real Codex ไม่พบ

รัน:

```zsh
find /Applications/Codex.app/Contents/Resources -type f \( -name codex -o -name codex-cli \) -perm -111 -print
```

ถ้าได้หนึ่ง path ให้ส่ง path นั้นแก่ installer:

```zsh
cd ~/Desktop/Codex/KIMMIZO_MAC_COMPLETE_BUNDLE
./install.sh --real-codex '/absolute/path/ที่พบ'
```

ห้ามเลือก `kimmizo-auto` เป็น real Codex เพราะจะเกิดการเรียกวน ตัวติดตั้งจะปฏิเสธกรณีนี้อัตโนมัติ

## การใช้งาน

- เลือก `✦ Auto` เมื่อต้องการให้ระบบปรับโมเดลและ effort ตามช่วงงาน
- เรียกชื่อ “เลขาคิม” ในแชทเพื่อเปิดบุคลิกภาษาไทยของเลขาคิมใน task นั้น
- พิมพ์ `เริ่มงานใหม่:` เมื่อต้องการให้ Auto ประเมินระดับงานใหม่แทนการรักษาระดับเดิม
- งานระดับ Ultra ต้องยืนยันด้วยข้อความ `อนุมัติ` ก่อน

## ถอนการติดตั้ง

```zsh
cd ~/Desktop/Codex/KIMMIZO_MAC_COMPLETE_BUNDLE
./uninstall.sh
```

ปิด Codex ด้วย `Command-Q` แล้วเปิดใหม่หลังถอน
