# Kimmizo Setup — Kimweaver v2 with v1 compatibility

Bootstrap สำหรับสร้าง **เลขาคิม** และทีมลูกน้องประจำโปรเจกต์ใหม่ค่ะ ระบบตรวจเครื่องและโปรเจกต์จริง เลือกเครื่องมือจากงานที่บอสสั่ง สร้าง Custom Agents พร้อม Model/Reasoning วาง Checkpoint กับ Memory และไม่โหลด Skill ทั้งหมดเข้า Context พร้อมกัน

Kimweaver v2 เป็น execution/assurance core กลางของระบบ ส่วน Kimmizo Setup เป็นตัวติดตั้งและ migration adapter แบบ project-local โปรเจกต์ที่ setup แล้วใช้ `.agents/skills/kimweaver/` และ `.kimmizo/core/manifest.json` ของตัวเอง จึงไม่ต้องอ่าน Home Base ตอน runtime ค่ะ CLI และ JSON เดิมยังคงใช้ได้ตลอดสาย v2.x โดยข้อมูล canonical v2 อยู่ใต้ key `v2` และ state อยู่ใน `.kimmizo/runtime/tasks/`

## ใช้งานครั้งแรก

เปิด PowerShell ใน Repo นี้ แล้วระบุโปรเจกต์ปลายทาง:

```powershell
.\install.ps1 -Target D:\TK-Project\โปรเจกต์ใหม่
```

คำสั่งที่ใช้ภายหลัง:

```powershell
.\install.ps1 -Mode doctor -Target D:\TK-Project\โปรเจกต์ใหม่
.\install.ps1 -Mode update -Target D:\TK-Project\โปรเจกต์ใหม่
.\install.ps1 -Mode repair -Target D:\TK-Project\โปรเจกต์ใหม่
.\install.ps1 -Mode team-report -Target D:\TK-Project\โปรเจกต์ใหม่
.\install.ps1 -Mode auto-status -Target D:\TK-Project\โปรเจกต์ใหม่
.\install.ps1 -Mode auto-uninstall -Target D:\TK-Project\โปรเจกต์ใหม่
```

คำสั่ง workflow/capsule v2:

```powershell
python plugins\kimmizo-setup\scripts\kimmizo.py capsule-status --target D:\path\project --json
python plugins\kimmizo-setup\scripts\kimmizo.py task-start --target D:\path\project --task "เป้าหมายงาน" --json
python plugins\kimmizo-setup\scripts\kimmizo.py task-status --target D:\path\project --task-id TASK_UUID --json
python plugins\kimmizo-setup\scripts\kimmizo.py task-transition --target D:\path\project --task-id TASK_UUID --state in_progress --json
python plugins\kimmizo-setup\scripts\kimmizo.py task-transition --target D:\path\project --task-id TASK_UUID --state checkpoint_ready --json
python plugins\kimmizo-setup\scripts\kimmizo.py task-transition --target D:\path\project --task-id TASK_UUID --state parent_verified --evidence tests\parent-proof.json --json
python plugins\kimmizo-setup\scripts\kimmizo.py task-transition --target D:\path\project --task-id TASK_UUID --state review_ready --review-attempt-id REVIEW_ATTEMPT --json
python plugins\kimmizo-setup\scripts\kimmizo.py task-transition --target D:\path\project --task-id TASK_UUID --state in_progress --review-attempt-id REVIEW_ATTEMPT --review-outcome unusable --review-evidence "reviewer returned no verdict" --json
python plugins\kimmizo-setup\scripts\kimmizo.py task-validate --target D:\path\project --task-id TASK_UUID --json
python plugins\kimmizo-setup\scripts\kimmizo.py capsule-rollback --target D:\path\project --json
```

- `-SkipInstall` สร้าง Project Capsule โดยไม่ติดตั้ง Capability จาก Registry แต่ยังติดตั้ง `✦ Auto` ใน Codex; ใช้ `-NoAutoModel` เมื่อต้องการข้ามส่วนนี้ด้วย
- `-DryRun` แสดงสิ่งที่จะทำโดยไม่แก้ไฟล์
- `-NoPluginRegistration` ไม่ลงทะเบียน Plugin นี้กับ Codex
- `-NoAutoModel` ไม่ติดตั้งหรืออัปเดตตัวเลือก `✦ Auto` ใน Codex

Setup รันซ้ำได้โดยไม่สร้าง Profile revision ใหม่ และไม่ทับเนื้อหาที่โปรเจกต์มีอยู่เดิมค่ะ

## สิ่งที่ Setup สร้าง

- `AGENTS.md` และ `.codex/config.toml` ผ่าน managed block ที่มี version/checksum
- `.codex/agents/*.toml` สำหรับ Explorer, Implementer, Reviewer และ Context Keeper
- `.agents/skills/kimmizo-*` สำหรับ Persona, Routing และ Memory
- `.agents/skills/kimweaver/` เป็น snapshot ที่ version/hash-bound สำหรับ execution, assurance, schemas และ domain adapters
- `.kimmizo/` สำหรับ Project Profile, Capability Index, Team revisions, Checkpoint และ Knowledge
- `.kimmizo/core/` สำหรับ active capsule manifest, standalone stdlib runtime, migration receipt และ previous v2 revisions
- `.gitignore` สำหรับ Memory, Runtime และ Install receipts ที่เป็นข้อมูลเฉพาะเครื่อง

ชื่อลูกน้องกับ `agent_id` คงเดิมตลอดอายุโปรเจกต์ แต่ Model, Reasoning, Personality, Instructions และ Allowlisted Skills ออกรุ่นใหม่ได้ โดยมีผลกับการ Spawn รอบถัดไปเท่านั้น

กติกา Model แยกเป็นสองส่วนค่ะ:

- `Auto` ในหัวข้อนี้หมายถึง Model ของ **เลขาคิมใน Task หลัก** เท่านั้น ไม่ใช่ Model ของ Custom Agent/ลูกน้อง
- Setup ติดตั้ง `✦ Auto` เข้า Model Picker ของ Codex ผ่าน App-server host extension แบบย้อนกลับได้ ไม่สร้างหน้าต่างหรือ Launcher แยก ไม่แก้ไฟล์ Codex ที่เซ็นไว้ และไม่เขียนชื่อโมเดลเสมือนลง `config.toml`
- เมื่อเลือก `✦ Auto` คิมใช้โหมด **ChatGPT Plus Limit-First** และยึดโมเดลเดิมในช่วงงานเดียวกันเพื่อรักษา prompt cache: ค่าเริ่มต้น/งานสั้นใช้ `gpt-5.6-luna/low`, งานเขียนโค้ดทั่วไปใช้ `gpt-5.6-luna/medium`, งานซับซ้อนหรือคลุมเครือจริงใช้ `gpt-5.6-terra/high`, และงาน production/security/database migration/ความเสี่ยงสูงเท่านั้นจึงใช้ `gpt-5.6-sol/high`
- `gpt-6-astra`, Max และ Ultra เป็น manual-only: Auto ไม่เลือกเองและคิมต้องขออนุมัติบอสก่อนทุกครั้ง งานที่เข้าเกณฑ์ Ultra จะพักที่ `high` เพื่อถามก่อน แล้วจึงใช้ `ultra` หลังได้รับอนุมัติในข้อความถัดไป
- ทำงานแบบอนุกรมและ solo เป็นค่าเริ่มต้น ไม่เปิดหลายเอเจนต์อัตโนมัติ ใช้ focused tests/lint/type-check/build หรือ read-only inspection ก่อนขยับโมเดล และปิด Fast mode เพื่อรักษาลิมิต
- ส่วนเสริมเก็บเฉพาะ Thread ID และผลการเลือก Model/Reasoning ล่าสุดเพื่อให้สถานะ Auto อยู่ต่อหลังเปิดแอปใหม่ ไม่เก็บข้อความ รูป ไฟล์ หรือ Token ของบอส
- การติดตั้งสำรองค่า `CODEX_CLI_PATH` เดิมและปฏิเสธการทับค่าที่เครื่องมืออื่นควบคุม ใช้ `-Mode auto-uninstall` เพื่อคืนค่าเดิม แล้วเปิด Codex ใหม่
- เมื่องานได้รับอนุญาตให้ใช้ลูกน้อง คิมเลือก Model/Reasoning ตามบันได Luna → Terra → Sol จาก Model Catalog ของ Host และไม่มอบ Astra อัตโนมัติ
- ก่อนเริ่มงานแต่ละส่วน คิมจะแจ้งผู้ทำ Model, Reasoning และเหตุผลที่เลือก; ถ้าใช้ Auto จะบอกโมเดลจริงเฉพาะเมื่อ Host แสดงให้เห็น และจะแจ้ง Agent/Model/Reasoning ก่อน spawn ลูกน้องทุกครั้ง

ผลจาก Router แยกเป็น `secretary_model_advice` สำหรับเลขาคิม และ `worker_model_selection` สำหรับลูกน้องค่ะ

Router v2 เลือก functional role ก่อน backend: Mira สำรวจ, Arin ผลิตงาน, Vera review แบบ read-only และ Nami บีบ checkpoint จากนั้นจึงผูก Model/Reasoning ที่ Host รองรับ งาน routine ใน `auto` ทำแบบ solo; explicit team ที่ไม่มี backend จะ block แทนการ downgrade เงียบค่ะ

เมื่อเข้าสู่ `review_ready` ระบบจะจอง attempt ที่มี ID คงที่และหัก budget แบบ atomic ก่อนเรียก Vera ทุกครั้ง ผล review ต้องอ้าง ID เดียวกัน; call ที่ล้มหรือไม่คืน verdict ยังคงถูกนับเป็น `unusable` เพื่อไม่ให้ retry เกิน hard maximum ค่ะ

Kimmizo Auto ใช้ `model-policy.json` ชุดเดียวกับ capsule และ inject minimal `ฉัน/ค่ะ` context เฉพาะ thread ที่ผู้ใช้เรียก “เลขาคิม” เท่านั้น งาน Auto ทั่วไปไม่รับ context นี้ ก่อน inject ระบบตรวจ active `kimmizo-capsule-v2` manifest และผูก SHA-256 กับ bytes ของ bootstrap จริง; หาก manifest/major/bootstrap ไม่ผ่าน substantive secretary turn จะ fail closed และแนะนำ `doctor/repair` ค่ะ ข้อความอนุมัติ/ปฏิเสธล้วนยังใช้ flow เดิมได้ แต่ข้อความที่ปนคำสั่งทำงานถือเป็น substantive เสมอค่ะ

Profile รุ่นใหม่จะเป็น Candidate ก่อน ยังไม่เปลี่ยนลูกน้อง Active จนกว่างานทดลองจะผ่านและมี Evidence:

```powershell
python plugins\kimmizo-setup\scripts\kimmizo.py team-update --target D:\path\project --name arin --model gpt-5.6-luna --reasoning medium --json
python plugins\kimmizo-setup\scripts\kimmizo.py team-evaluate --target D:\path\project --name arin --revision 2 --result passed --evidence tests\team-eval.json --json
```

## Routing หลัก

```text
รับงาน → จำแนกประเภท/ความเสี่ยง → ดู Capability metadata
→ เลือกลูกน้องและ Profile → ส่ง Context packet ขนาดเล็ก
→ ทำงาน/ตรวจหลักฐาน → Checkpoint → คิมสรุปให้บอส
```

ลำดับงาน UI คือ File/API/Connector → Browser → Chrome session เดิม → Computer Use ทางการ และกัน Community `computer-use` ฝั่ง Linux บน Windows ค่ะ

## ขอบเขตความปลอดภัย

ติดตั้งอัตโนมัติเฉพาะรายการที่อยู่ใน `baseline-lock.json` และไม่เพิ่ม Auth, Hook, MCP, Permission, Sandbox หรือ External write ใหม่ รายการเหล่านี้จะหยุดเป็น `approval_required` เพื่อให้บอสอนุมัติผ่านระบบหนึ่งครั้ง

หลังบอสอนุมัติสิทธิ์ในระบบแล้ว ให้บันทึก Approval ที่ผูกกับ Registry/Lock รุ่นนั้น แล้วสั่ง Update ต่อ หาก Registry หรือ Lock เปลี่ยน Approval เดิมจะใช้ไม่ได้อัตโนมัติ:

```powershell
python plugins\kimmizo-setup\scripts\kimmizo.py capability-approve --target D:\path\project --id data-analytics --json
.\install.ps1 -Mode update -Target D:\path\project
```

`capability-approve` ไม่ได้ให้สิทธิ์เองค่ะ คำสั่งนี้รับรองได้เฉพาะ Plugin ที่บอสติดตั้ง/อนุมัติผ่าน Codex Host และอยู่ในสถานะ enabled แล้ว จากนั้น Receipt จะผูกกับ Selector, Manifest, ไฟล์อ้างอิง และลายนิ้วมือของแพ็กเกจทั้งหมด หากแพ็กเกจหรือสิทธิ์เปลี่ยน Receipt เดิมจะใช้ไม่ได้

Kimmizo ปิดไฟล์ routing แบบ always-on ของ `using-superpowers` จริง และเก็บ named subskills ไว้ให้ Router เลือกเฉพาะขั้นที่ต้องใช้ การอัปเดต Marketplace อาจนำไฟล์ดังกล่าวกลับมา ดังนั้น `update`/`repair` จะตรวจและปิดซ้ำพร้อม Receipt ค่ะ

สิทธิ์ `sandbox_mode` ของลูกน้องถูกบังคับโดย Host ส่วน Skill/Tool/MCP allowlist ใน Custom Agent v1 เป็นนโยบายใน instructions และคิมต้องไม่ส่งเครื่องมือที่อยู่นอกสิทธิ์เข้า Context ของลูกน้องค่ะ

Pinned community skills ตรวจทั้ง Archive SHA256 และ `SKILL.md` SHA256 มี Backup/Receipt และ Rollback แบบ transaction ส่วน Plugin/CLI ที่ติดตั้งผ่าน Registry มีคำสั่ง Rollback แบบ allowlist:

```powershell
python plugins\kimmizo-setup\scripts\kimmizo.py capability-rollback --target D:\path\project --id grill-me --json
```

v1 ไม่มี Cross-project memory, Vector DB หรือ Telemetry และไม่มี dependency ไปโปรเจกต์เลขาคิมอื่นค่ะ Checkpoint และ Long-term lessons ถูก Git-ignore โดยค่าเริ่มต้น

## พัฒนาและตรวจสอบ

```powershell
python -m pip install pytest
python -m pytest -q
python scripts\validate_repo.py
```

## Automatic Codex runtime updates

Kimmizo Auto checks the latest signed Codex Desktop runtime every time its proxy starts. It automatically discovers and updates the complete verified runtime bundle, including `codex-real.exe`, code-mode host, command runner, Windows sandbox setup, and future signed `codex-*.exe` companions. If an update is unavailable, invalid, or locked, the proxy keeps the previous verified bundle and retries automatically on the next start.

เอกสาร Custom Agent อ้างอิง [Codex Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents)
