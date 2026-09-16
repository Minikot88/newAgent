package app

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func writeRuntimeFixture(t *testing.T) string {
	t.Helper()
	home := t.TempDir()
	policy := []byte(`{"schema_version":1,"policy_version":"test","routes":{"fast":{"models":["gpt-test"],"efforts":["low"]},"balanced":{"models":["gpt-test"],"efforts":["medium"]},"deep":{"models":["gpt-test"],"efforts":["high"]},"critical":{"models":["gpt-test"],"efforts":["high"]},"ultra":{"models":["gpt-test"],"efforts":["high"],"requires_approval":true}}}`)
	voice := []byte(`{"schema_version":1,"policy_version":"test","name":"อาเทน่า","trigger":"อาเทน่า","language":"th","pronoun":"ฉัน","ending":"ค่ะ","instruction":"ให้แทนตัวเองว่า ฉัน และลงท้ายว่า ค่ะ","stores_prompts":false}`)
	writeVerified := func(name string, contents []byte) {
		t.Helper()
		if err := os.WriteFile(filepath.Join(home, name), contents, 0o600); err != nil {
			t.Fatal(err)
		}
		sum := sha256.Sum256(contents)
		if err := os.WriteFile(filepath.Join(home, name[:len(name)-len(filepath.Ext(name))]+".sha256"), []byte(hex.EncodeToString(sum[:])+"\n"), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	writeVerified("model-policy.json", policy)
	writeVerified("voice-bootstrap.json", voice)
	realCLI := filepath.Join(home, "real-codex")
	if err := os.WriteFile(realCLI, []byte("fixture"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(home, "real-codex.path"), []byte(realCLI+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	return home
}

func TestStatusFailsWhenPolicyAndVoiceVersionsDiffer(t *testing.T) {
	home := writeRuntimeFixture(t)
	voicePath := filepath.Join(home, "voice-bootstrap.json")
	voice := []byte(`{"schema_version":1,"policy_version":"other","name":"อาเทน่า","trigger":"อาเทน่า","language":"th","pronoun":"ฉัน","ending":"ค่ะ","instruction":"ให้แทนตัวเองว่า ฉัน และลงท้ายว่า ค่ะ","stores_prompts":false}`)
	if err := os.WriteFile(voicePath, voice, 0o600); err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(voice)
	if err := os.WriteFile(filepath.Join(home, "voice-bootstrap.sha256"), []byte(hex.EncodeToString(sum[:])+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	var stdout, stderr bytes.Buffer
	code := Run([]string{"--athena-status"}, nil, &stdout, &stderr, []string{"ATHENA_HOME=" + home}, filepath.Join(home, "athena-auto"))
	if code == 0 {
		t.Fatalf("mismatched policy/voice versions passed: %s", stdout.String())
	}
}

func TestStatusReportsVerifiedPromptFreeRuntime(t *testing.T) {
	home := writeRuntimeFixture(t)
	var stdout, stderr bytes.Buffer
	code := Run([]string{"--athena-status"}, nil, &stdout, &stderr, []string{"ATHENA_HOME=" + home}, filepath.Join(home, "athena-auto"))
	if code != 0 {
		t.Fatalf("exit=%d stderr=%s stdout=%s", code, stderr.String(), stdout.String())
	}
	var status Status
	if err := json.Unmarshal(stdout.Bytes(), &status); err != nil {
		t.Fatal(err)
	}
	if status.Status != "ready" || !status.PolicyVerified || !status.VoiceVerified || !status.RealCLIExecutable {
		t.Fatalf("unexpected status: %#v", status)
	}
	if status.VirtualModel != "athena-auto" || status.DisplayName != "✦ Auto" || status.StoresPrompts {
		t.Fatalf("unsafe or incorrect identity: %#v", status)
	}
	if !bytes.Contains(stdout.Bytes(), []byte(`"secretsCopied":false`)) {
		t.Fatalf("status does not explicitly attest secretsCopied=false: %s", stdout.String())
	}
	if !status.OutboundModelGuard {
		t.Fatalf("status does not attest the outbound model guard: %#v", status)
	}
}

func TestDefaultAutoCommandsRoundTrip(t *testing.T) {
	home := writeRuntimeFixture(t)
	var stdout, stderr bytes.Buffer
	environ := []string{"ATHENA_HOME=" + home}
	if code := Run([]string{"--athena-default-auto-on"}, nil, &stdout, &stderr, environ, filepath.Join(home, "athena-auto")); code != 0 {
		t.Fatalf("enable exit=%d stderr=%s", code, stderr.String())
	}
	stdout.Reset()
	stderr.Reset()
	if code := Run([]string{"--athena-status"}, nil, &stdout, &stderr, environ, filepath.Join(home, "athena-auto")); code != 0 {
		t.Fatalf("status exit=%d stderr=%s", code, stderr.String())
	}
	var status Status
	if err := json.Unmarshal(stdout.Bytes(), &status); err != nil {
		t.Fatal(err)
	}
	if !status.DefaultAuto {
		t.Fatal("default Auto was not persisted")
	}
	stdout.Reset()
	stderr.Reset()
	if code := Run([]string{"--athena-default-auto-off"}, nil, &stdout, &stderr, environ, filepath.Join(home, "athena-auto")); code != 0 {
		t.Fatalf("disable exit=%d stderr=%s", code, stderr.String())
	}
}

func TestSelfTestFailsClosedWhenPolicyIsTampered(t *testing.T) {
	home := writeRuntimeFixture(t)
	if err := os.WriteFile(filepath.Join(home, "model-policy.json"), []byte(`{"schema_version":1}`), 0o600); err != nil {
		t.Fatal(err)
	}
	var stdout, stderr bytes.Buffer
	code := Run([]string{"--athena-self-test"}, nil, &stdout, &stderr, []string{"ATHENA_HOME=" + home}, filepath.Join(home, "athena-auto"))
	if code == 0 {
		t.Fatalf("tampered policy passed self-test: %s", stdout.String())
	}
}
