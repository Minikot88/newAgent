# Kimmizo Windows Bundle Check

ตรวจเมื่อ 2026-09-15 จากชุด `KIMMIZO_WINDOWS_COMPLETE_BUNDLE`

## ผลตรวจ

- ชุดย้ายเครื่องอยู่ใน `D:\git\new\KIMMIZO_WINDOWS_COMPLETE_BUNDLE`
- ไม่พบ `.git`, `.worktrees` หรือ `__pycache__`
- PowerShell syntax ของ `install.ps1`, Auto installer และ runtime sync ผ่าน
- `install.ps1 -DryRun -NoPluginRegistration -NoAutoModel` จบด้วย exit code 0
- มี Kimmizo Auto installer, C# proxy, runtime sync และ model policy ครบ
- มีโครงสร้าง project capsule, skills, templates และ tests ครบ

## ข้อจำกัดที่ยังยืนยันไม่ได้บนเครื่องนี้

- ยังไม่ได้ติดตั้งจริงบน Windows เครื่องปลายทาง เพราะการติดตั้งจริงจะเปลี่ยน user profile, Codex CLI path และ runtime ของเครื่องนั้น
- ชุดทดสอบ pytest ยังรันไม่ได้ใน environment ตรวจ เพราะไม่มีโมดูล `pytest`
- validator พบข้อมูลเดิมไม่ตรงกัน: vendor voice bootstrap ใช้ `schemaVersion: 3` แต่ validator ในชุดนี้ยังคาด `schemaVersion: 2`
- Auto จะทำงานจริงได้เมื่อเครื่องปลายทางมี Codex Desktop และ prerequisite ที่ installer ตรวจพบ/ติดตั้งได้ เช่น Python, .NET Framework และ winget

## สรุป

สถานะคือ **พร้อมนำไปทดสอบติดตั้งบน Windows เครื่องอื่น แต่ยังไม่ใช่การยืนยันติดตั้งจริง 100%**

คำสั่งติดตั้ง:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1 -Target "$HOME\Documents\KimmizoProject"
```

ตรวจ Auto หลังติดตั้ง:

```powershell
.\install.ps1 -Mode auto-status
```
