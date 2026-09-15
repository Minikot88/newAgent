# Kimmizo — ChatGPT Plus Limit-First

นโยบายนี้ให้ **ประหยัดลิมิตมาก่อน**, แล้วรักษาความฉลาดและความถูกต้องด้วยการตรวจสอบแบบ deterministic ค่ะ ความเร็วไม่ใช่เป้าหมายหลัก

## ลำดับการเลือกโมเดล

| งาน | Model | Reasoning |
|---|---|---|
| ค่าเริ่มต้น งานสั้น อ่าน สรุป แก้เล็กน้อย | `gpt-5.6-luna` | `low` |
| เขียนโค้ดทั่วไป ฟีเจอร์/บั๊กที่ขอบเขตชัด | `gpt-5.6-luna` | `medium` |
| งานซับซ้อน คลุมเครือ สถาปัตยกรรม หรือ root cause | `gpt-5.6-terra` | `high` |
| production, security, database migration หรือการตัดสินใจความเสี่ยงสูง | `gpt-5.6-sol` | `high` |
| `gpt-6-astra`, Max, Ultra | ใช้เมื่อบอสอนุมัติเท่านั้น | ตามที่อนุมัติ |

## กติกาการทำงาน

1. เริ่มด้วย Luna และใช้ไฟล์/บริบทเท่าที่จำเป็นค่ะ
2. รัน focused tests, lint, type-check, build หรือ read-only inspection ก่อนขยับโมเดลค่ะ
3. ทำงานแบบอนุกรมและ solo เป็นค่าเริ่มต้น ห้ามเปิดหลายเอเจนต์อัตโนมัติค่ะ
4. ใช้ทีมเมื่อบอสสั่งชัดเจนเท่านั้น; reviewed/protected ที่เลือกชัดเจนอาจใช้ Reviewer แบบ read-only หนึ่งคนค่ะ
5. ปิด Fast mode และรักษาโมเดลเดิมใน phase เดียวเพื่อใช้ prompt cache ค่ะ
6. ห้าม Auto เลือก Astra; คิมต้องถามบอสก่อน Astra ทุกครั้งค่ะ
7. Ultra ต้องขออนุมัติใหม่ทุก activation ค่ะ

แหล่งอ้างอิงทางการที่ใช้กำหนดนโยบาย: [Codex pricing](https://learn.chatgpt.com/docs/pricing), [Codex models](https://learn.chatgpt.com/docs/models), และ [latest model guide](https://developers.openai.com/api/docs/guides/latest-model) ค่ะ
