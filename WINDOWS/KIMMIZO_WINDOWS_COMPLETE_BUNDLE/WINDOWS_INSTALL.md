# Kimmizo Windows Complete Bundle

ชุดติดตั้งเลขาคิมสำหรับ Windows แบบย้ายเครื่องได้ โดยไม่ต้องนำ Git repository ติดไปด้วย

## ติดตั้ง

เปิด PowerShell ในโฟลเดอร์นี้ แล้วรัน:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1 -Target "$HOME\Documents\KimmizoProject"
```

ถ้าต้องการตรวจสถานะ Auto:

```powershell
.\install.ps1 -Mode auto-status
```

ถอน Auto:

```powershell
.\install.ps1 -Mode auto-uninstall
```

ไม่ต้องคัดลอก `.git`, ไม่ต้องติดตั้ง Git repository และห้ามคัดลอก secrets, token หรือไฟล์ `.env` จากเครื่องเดิม
