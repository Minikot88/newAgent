#!/bin/zsh
set -euo pipefail
IFS=$'\n\t'

[[ $# -eq 1 ]] || {
  print -u2 -r -- "Usage: ./name.sh 'assistant name'"
  exit 64
}

ASSISTANT_NAME="$1"
[[ -n "$ASSISTANT_NAME" && ${#ASSISTANT_NAME} -le 80 && "$ASSISTANT_NAME" != */* && "$ASSISTANT_NAME" != *$'\n'* && "$ASSISTANT_NAME" != *$'\r'* && "$ASSISTANT_NAME" != *$'\t'* ]] || {
  print -u2 -r -- "ชื่อไม่ถูกต้อง: ต้องไม่ว่าง ไม่เกิน 80 ตัวอักษร และห้ามมี / หรือ control characters"
  exit 64
}

INSTALL_ROOT="$HOME/.kimmizo-secretary/auto"
RECEIPT="$INSTALL_ROOT/install.json"
VOICE="$INSTALL_ROOT/voice-bootstrap.json"
VOICE_HASH="$INSTALL_ROOT/voice-bootstrap.sha256"
LABEL="com.kimmizo.kimmizo-auto"

[[ -f "$RECEIPT" && -f "$VOICE" && -f "$VOICE_HASH" ]] || {
  print -u2 -r -- "Kimmizo installation is incomplete; name was not changed."
  exit 66
}
receipt_root="$(/usr/bin/plutil -extract installRoot raw -o - "$RECEIPT" 2>/dev/null || true)"
receipt_label="$(/usr/bin/plutil -extract Label raw -o - "$RECEIPT" 2>/dev/null || true)"
[[ "$receipt_root" == "$INSTALL_ROOT" && "$receipt_label" == "$LABEL" ]] || {
  print -u2 -r -- "Kimmizo receipt failed ownership validation; name was not changed."
  exit 65
}

VOICE_TEMP="$(/usr/bin/mktemp "$INSTALL_ROOT/.voice.tmp.XXXXXX")"
HASH_TEMP="$(/usr/bin/mktemp "$INSTALL_ROOT/.voice-hash.tmp.XXXXXX")"
RECEIPT_TEMP="$(/usr/bin/mktemp "$INSTALL_ROOT/.receipt.tmp.XXXXXX")"
SUCCESS=0
cleanup() {
  exit_code=$?
  [[ $SUCCESS -eq 1 ]] || print -u2 -r -- "Name configuration failed; installed files were left unchanged."
  /bin/rm -f "$VOICE_TEMP" "$HASH_TEMP" "$RECEIPT_TEMP"
  return $exit_code
}
trap cleanup EXIT INT TERM

/bin/cp "$VOICE" "$VOICE_TEMP"
/usr/bin/plutil -replace configured -bool YES "$VOICE_TEMP"
/usr/bin/plutil -replace name -string "$ASSISTANT_NAME" "$VOICE_TEMP"
/usr/bin/plutil -replace trigger -string "$ASSISTANT_NAME" "$VOICE_TEMP"
/usr/bin/plutil -replace instruction -string "คุณคือ ‘$ASSISTANT_NAME’ เลขาผู้ช่วยผู้หญิงของผู้ใช้ ใช้ภาษาไทยเป็นหลัก แทนตัวเองว่า ‘ฉัน’ และลงท้ายประโยคภาษาไทยอย่างสุภาพด้วย ‘ค่ะ’ ทำงานเชิงรุกภายในขอบเขตที่ได้รับอนุญาต และห้ามอ่าน แสดง คัดลอก หรือสรุปข้อมูลลับค่ะ" "$VOICE_TEMP"
/usr/bin/plutil -convert json "$VOICE_TEMP"
/usr/bin/shasum -a 256 "$VOICE_TEMP" | /usr/bin/awk '{print $1}' > "$HASH_TEMP"

/bin/cp "$RECEIPT" "$RECEIPT_TEMP"
if /usr/bin/plutil -extract secretaryName raw -o - "$RECEIPT_TEMP" >/dev/null 2>&1; then
  /usr/bin/plutil -replace secretaryName -string "$ASSISTANT_NAME" "$RECEIPT_TEMP"
else
  /usr/bin/plutil -insert secretaryName -string "$ASSISTANT_NAME" "$RECEIPT_TEMP"
fi
/usr/bin/plutil -replace nameConfigured -bool YES "$RECEIPT_TEMP"
/usr/bin/plutil -convert json "$RECEIPT_TEMP"

/bin/chmod 600 "$VOICE_TEMP" "$HASH_TEMP" "$RECEIPT_TEMP"
/bin/mv "$VOICE_TEMP" "$VOICE"
/bin/mv "$HASH_TEMP" "$VOICE_HASH"
/bin/mv "$RECEIPT_TEMP" "$RECEIPT"

if [[ -x "$INSTALL_ROOT/kimmizo-auto" ]]; then
  "$INSTALL_ROOT/kimmizo-auto" --athena-self-test >/dev/null
fi

SUCCESS=1
trap - EXIT INT TERM
print -r -- "PASS: assistant name configured. Quit Codex with Command-Q and reopen it."
