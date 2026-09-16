# ตรวจรับ Kimmizo Auto บน Mac

## Runtime

รัน `./status.sh` ต้องได้ exit code `0` และยืนยัน:

- `status` เป็น `ready`
- `hostOs` เป็น `darwin` และ `hostArch` เป็น `arm64`
- `policyVerified`, `voiceVerified`, `realCliExecutable` และ `outboundModelGuard` เป็น `true`
- `storesPrompts` และ `secretsCopied` เป็น `false`
- LaunchAgent และ `CODEX_CLI_PATH` active
- `✦ Auto` อยู่ใน installed local catalog

## Routing จริง

เลือก `✦ Auto` แล้วเริ่ม ephemeral/read-only task ระบบต้องส่ง official model slug ที่อยู่ใน catalogเข้า real Codex และต้องไม่ส่ง `athena-auto` ออกไป Outbound guard ต้องปฏิเสธ method ใหม่ที่มี virtual slug ซึ่ง runtime ยังไม่รู้จัก

## บุคลิกและชื่อ

ก่อน verification เสร็จ `nameConfigured` ต้องเป็น `false` หลังผู้ใช้ตอบชื่อแล้วจึงรัน `./name.sh "ชื่อ"`, ปิด Codex ด้วย `Command-Q`, เปิดใหม่ และตรวจ `./status.sh` อีกครั้ง

## เกณฑ์ผ่าน

ถือว่าผ่านเมื่อ bundle manifest, unit/integration tests, native self-test, installer, status, real app-server routing และ Codex restart ให้ exit code สำเร็จทั้งหมด ห้ามสรุปจากการเห็นชื่อ `✦ Auto` เพียงอย่างเดียว
