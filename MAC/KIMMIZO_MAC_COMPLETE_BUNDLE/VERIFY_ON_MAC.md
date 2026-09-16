# ตรวจรับบน Mac

รัน checklist นี้หลังติดตั้งและปิด/เปิด Codex ใหม่แล้ว

## 1. ตรวจสถานะ runtime

```zsh
cd ~/Desktop/Codex/KIMMIZO_MAC_COMPLETE_BUNDLE
./status.sh
```

ต้องเห็น JSON ที่มีค่าหลักดังนี้:

```json
{
  "status": "ready",
  "virtualModel": "athena-auto",
  "displayName": "✦ Auto",
  "storesPrompts": false,
  "secretsCopied": false,
  "policyVerified": true,
  "voiceVerified": true,
  "realCliExecutable": true
}
```

และต้องมีบรรทัดทั้ง `PASS: LaunchAgent and CODEX_CLI_PATH are active for Kimmizo.` และ `PASS: ✦ Auto is present in the installed Codex model catalog.`

## 2. ตรวจใน Codex UI

1. เปิด task ใหม่
2. เปิดเมนู Model
3. ยืนยันว่ามี `✦ Auto`
4. เลือก `✦ Auto`

## 3. ตรวจบุคลิก

ส่งข้อความ:

```text
เลขาคิม ช่วยสรุปว่าเธอจะทำงานกับโปรเจกต์นี้อย่างไรแบบสั้น ๆ
```

ผลที่คาดหวัง: ตอบในบุคลิกผู้หญิง ใช้สรรพนาม `ฉัน` และลงท้ายอย่างสุภาพด้วย `ค่ะ`

## 4. ตรวจ Auto แบบปลอดภัย

ส่งงานอ่านอย่างเดียว เช่น:

```text
เริ่มงานใหม่: อ่าน README แล้วสรุปสั้น ๆ โดยไม่แก้ไฟล์
```

จากนั้นรัน `./status.sh` อีกครั้ง ค่า `routeCount` ควรมากกว่า `0`

## ถ้า `✦ Auto` ยังไม่ปรากฏ

1. ตรวจว่าใช้ `Command-Q` ไม่ใช่เพียงปิดหน้าต่าง
2. รัน `./status.sh` และเก็บ output ทั้งหมด
3. ตรวจค่า active path:

   ```zsh
   launchctl getenv CODEX_CLI_PATH
   ```

   ต้องเป็น `/Users/<ชื่อผู้ใช้>/.kimmizo-secretary/auto/kimmizo-desktop-entrypoint`

4. ถ้าสถานะไม่ใช่ `ready` หรือ Model ยังไม่ขึ้น ให้รัน installer ซ้ำจาก root ของ bundle แล้วปิด Codex ด้วย `Command-Q` ก่อนเปิดใหม่:

   ```zsh
   ./install.sh --name "ชื่อที่เลือก"
   ./status.sh
   ```

5. หากยังไม่ขึ้น ให้ส่งเฉพาะ output จาก `./status.sh` และผลของ `launchctl getenv CODEX_CLI_PATH` กลับมา โดยไม่ส่งข้อมูลบัญชีหรือไฟล์ส่วนตัว

สถานะ cross-build จาก Windows เพียงอย่างเดียวไม่ถือว่าผ่านขั้นนี้ ต้องเห็นผลจริงจาก Mac และ UI
