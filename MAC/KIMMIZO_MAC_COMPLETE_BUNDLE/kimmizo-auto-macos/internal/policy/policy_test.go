package policy

import (
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func writeVerifiedFixture(t *testing.T, name string, raw []byte) (string, string) {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, name)
	hashPath := path + ".sha256"
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(raw)
	if err := os.WriteFile(hashPath, []byte(fmt.Sprintf("%x\n", sum)), 0o600); err != nil {
		t.Fatal(err)
	}
	return path, hashPath
}

func fixturePolicyJSON() []byte {
	return []byte(`{
  "schema_version": 1,
  "policy_version": "1.0.0",
  "routes": {
    "fast": {"models":["gpt-5.6-luna","gpt-5.6-terra"],"efforts":["low","medium"]},
    "balanced": {"models":["gpt-5.6-terra","gpt-5.6-sol"],"efforts":["medium","high"]},
    "deep": {"models":["gpt-5.6-sol","gpt-6-astra"],"efforts":["high","xhigh"]},
    "critical": {"models":["gpt-6-astra","gpt-5.6-sol"],"efforts":["xhigh","high"]},
    "ultra": {"models":["gpt-6-astra"],"efforts":["ultra","max"],"requires_approval":true}
  }
}`)
}

func TestLoadVerifiedRejectsTamperedPolicy(t *testing.T) {
	path, hashPath := writeVerifiedFixture(t, "policy.json", fixturePolicyJSON())
	if err := os.WriteFile(path, []byte(`{"schema_version":1}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadVerified(path, hashPath); err == nil {
		t.Fatal("tampered policy was accepted")
	}
}

func TestLoadVerifiedRejectsUnsupportedSchema(t *testing.T) {
	raw := []byte(`{"schema_version":99,"policy_version":"bad","routes":{}}`)
	path, hashPath := writeVerifiedFixture(t, "policy.json", raw)
	if _, err := LoadVerified(path, hashPath); err == nil {
		t.Fatal("unsupported schema was accepted")
	}
}

func TestChooseUsesOnlyObservedModelAndEffort(t *testing.T) {
	path, hashPath := writeVerifiedFixture(t, "policy.json", fixturePolicyJSON())
	p, err := LoadVerified(path, hashPath)
	if err != nil {
		t.Fatal(err)
	}
	route, err := p.Choose("วิเคราะห์ architecture และ root cause", Catalog{
		Models: map[string][]string{"gpt-5.6-sol": {"high", "xhigh"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if route.Tier != "deep" || route.Model != "gpt-5.6-sol" || route.Effort != "high" {
		t.Fatalf("unexpected route: %#v", route)
	}
}

func TestChooseFallsBackWithinObservedCatalog(t *testing.T) {
	path, hashPath := writeVerifiedFixture(t, "policy.json", fixturePolicyJSON())
	p, err := LoadVerified(path, hashPath)
	if err != nil {
		t.Fatal(err)
	}
	route, err := p.Choose("เพิ่มหน้าตั้งค่าให้โปรเจกต์นี้", Catalog{
		Models: map[string][]string{"gpt-5.6-sol": {"high"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if route.Model != "gpt-5.6-sol" || route.Effort != "high" {
		t.Fatalf("unexpected fallback: %#v", route)
	}
}

func TestChooseFailsWhenNoVerifiedCandidateExists(t *testing.T) {
	path, hashPath := writeVerifiedFixture(t, "policy.json", fixturePolicyJSON())
	p, err := LoadVerified(path, hashPath)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := p.Choose("ตรวจ security ก่อน production deploy", Catalog{Models: map[string][]string{}}); err == nil {
		t.Fatal("routing succeeded without an observed model")
	}
}

func TestUltraRequiresExplicitApproval(t *testing.T) {
	path, hashPath := writeVerifiedFixture(t, "policy.json", fixturePolicyJSON())
	p, err := LoadVerified(path, hashPath)
	if err != nil {
		t.Fatal(err)
	}
	catalog := Catalog{Models: map[string][]string{"gpt-6-astra": {"ultra", "max"}}}
	route, err := p.Choose("ตรวจทั้งโค้ดเบสด้วยหลายเอเจนต์", catalog)
	if err != nil {
		t.Fatal(err)
	}
	if !route.RequiresApproval || route.Model != "" {
		t.Fatalf("ultra did not stop for approval: %#v", route)
	}
	route, err = p.ChooseApproved("ตรวจทั้งโค้ดเบสด้วยหลายเอเจนต์", catalog)
	if err != nil {
		t.Fatal(err)
	}
	if route.Model != "gpt-6-astra" || route.Effort != "ultra" || route.RequiresApproval {
		t.Fatalf("approved ultra did not route: %#v", route)
	}
}

func TestLoadVoiceVerifiedRejectsTampering(t *testing.T) {
	raw := []byte(`{"schema_version":1,"policy_version":"1.0.0","name":"อาเทน่า","trigger":"อาเทน่า","language":"th","pronoun":"ฉัน","ending":"ค่ะ","instruction":"ให้แทนตัวเองว่า ฉัน และลงท้ายว่า ค่ะ","stores_prompts":false}`)
	path, hashPath := writeVerifiedFixture(t, "voice.json", raw)
	if _, err := LoadVoiceVerified(path, hashPath); err != nil {
		t.Fatalf("valid voice rejected: %v", err)
	}
	if err := os.WriteFile(path, append(raw, ' '), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadVoiceVerified(path, hashPath); err == nil {
		t.Fatal("tampered voice was accepted")
	}
}

func TestLoadVoiceVerifiedRequiresInstruction(t *testing.T) {
	raw := []byte(`{"schema_version":1,"policy_version":"1.0.0","name":"อาเทน่า","trigger":"อาเทน่า","language":"th","pronoun":"ฉัน","ending":"ค่ะ","stores_prompts":false}`)
	path, hashPath := writeVerifiedFixture(t, "voice.json", raw)
	if _, err := LoadVoiceVerified(path, hashPath); err == nil {
		t.Fatal("voice without executable instruction was accepted")
	}
}
