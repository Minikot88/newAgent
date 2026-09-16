package proxy

import (
	"bytes"
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"athena-auto/internal/policy"
	"athena-auto/internal/state"
)

func transformerPolicy(t *testing.T) policy.Policy {
	t.Helper()
	raw := []byte(`{
  "schema_version":1,
  "policy_version":"1.0.0",
  "routes":{
    "fast":{"models":["gpt-5.6-luna","gpt-5.6-terra"],"efforts":["low","medium"]},
    "balanced":{"models":["gpt-5.6-terra","gpt-5.6-sol"],"efforts":["medium","high"]},
    "deep":{"models":["gpt-5.6-sol","gpt-6-astra"],"efforts":["high","xhigh"]},
    "critical":{"models":["gpt-6-astra","gpt-5.6-sol"],"efforts":["xhigh","high"]},
    "ultra":{"models":["gpt-6-astra"],"efforts":["ultra","max"],"requires_approval":true}
  }
}`)
	dir := t.TempDir()
	path := filepath.Join(dir, "policy.json")
	hashPath := path + ".sha256"
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(raw)
	if err := os.WriteFile(hashPath, []byte(fmt.Sprintf("%x\n", sum)), 0o600); err != nil {
		t.Fatal(err)
	}
	p, err := policy.LoadVerified(path, hashPath)
	if err != nil {
		t.Fatal(err)
	}
	return p
}

func newFixtureTransformer(t *testing.T) (*Transformer, string) {
	t.Helper()
	statePath := filepath.Join(t.TempDir(), "state.json")
	store, err := state.Load(statePath)
	if err != nil {
		t.Fatal(err)
	}
	voice := policy.Voice{SchemaVersion: 1, Name: "อาเทน่า", Trigger: "อาเทน่า", Language: "th", Pronoun: "ฉัน", Ending: "ค่ะ", Instruction: "ให้แทนตัวเองว่า ฉัน และลงท้ายว่า ค่ะ"}
	return NewTransformer(transformerPolicy(t), voice, store), statePath
}

func seedCatalog(t *testing.T, tr *Transformer) {
	t.Helper()
	forward, _, err := tr.ClientLine([]byte(`{"id":1,"method":"model/list","params":{}}`))
	if err != nil || len(forward) == 0 {
		t.Fatalf("model request: %s %v", forward, err)
	}
	response := []byte(`{"id":1,"result":{"data":[
      {"id":"gpt-5.6-luna","model":"gpt-5.6-luna","displayName":"Luna","isDefault":false,"supportedReasoningEfforts":[{"reasoningEffort":"low"},{"reasoningEffort":"medium"}]},
      {"id":"gpt-5.6-terra","model":"gpt-5.6-terra","displayName":"Terra","isDefault":true,"supportedReasoningEfforts":[{"reasoningEffort":"medium"},{"reasoningEffort":"high"}]},
      {"id":"gpt-5.6-sol","model":"gpt-5.6-sol","displayName":"Sol","isDefault":false,"supportedReasoningEfforts":[{"reasoningEffort":"high"},{"reasoningEffort":"xhigh"}]},
      {"id":"gpt-6-astra","model":"gpt-6-astra","displayName":"Astra","isDefault":false,"supportedReasoningEfforts":[{"reasoningEffort":"xhigh"},{"reasoningEffort":"max"},{"reasoningEffort":"ultra"}]}
    ]}}`)
	if _, err := tr.ServerLine(response); err != nil {
		t.Fatal(err)
	}
}

func TestModelListAddsAthenaAutoOnce(t *testing.T) {
	tr, _ := newFixtureTransformer(t)
	forward, _, err := tr.ClientLine([]byte(`{"id":1,"method":"model/list","params":{}}`))
	if err != nil || len(forward) == 0 {
		t.Fatalf("request: %s %v", forward, err)
	}
	got, err := tr.ServerLine([]byte(`{"id":1,"result":{"data":[{"id":"gpt-5.6-sol","model":"gpt-5.6-sol","displayName":"Sol","isDefault":true,"supportedReasoningEfforts":[{"reasoningEffort":"high"}]}]}}`))
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Count(got, []byte(`"athena-auto"`)) != 2 {
		t.Fatalf("virtual model not inserted exactly once: %s", got)
	}
	if !bytes.Contains(got, []byte(`"displayName":"✦ Auto"`)) {
		t.Fatalf("display name missing: %s", got)
	}
}

func TestModelListDoesNotDuplicateExistingVirtualModel(t *testing.T) {
	tr, _ := newFixtureTransformer(t)
	tr.ClientLine([]byte(`{"id":1,"method":"model/list","params":{}}`))
	got, err := tr.ServerLine([]byte(`{"id":1,"result":{"data":[{"id":"athena-auto","model":"athena-auto"},{"id":"gpt-5.6-sol","model":"gpt-5.6-sol","supportedReasoningEfforts":[{"reasoningEffort":"high"}]}]}}`))
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Count(got, []byte(`"athena-auto"`)) != 2 {
		t.Fatalf("virtual model duplicated: %s", got)
	}
}

func TestTurnStartRoutesAutoWithoutPersistingPrompt(t *testing.T) {
	tr, statePath := newFixtureTransformer(t)
	seedCatalog(t, tr)
	input := []byte(`{"id":2,"method":"turn/start","params":{"threadId":"t1","model":"athena-auto","input":[{"type":"text","text":"วิเคราะห์ architecture และ root cause"}]}}`)
	forward, immediate, err := tr.ClientLine(input)
	if err != nil {
		t.Fatal(err)
	}
	if len(immediate) != 0 {
		t.Fatalf("unexpected immediate response: %s", immediate)
	}
	if !bytes.Contains(forward, []byte(`"model":"gpt-5.6-sol"`)) || !bytes.Contains(forward, []byte(`"effort":"high"`)) {
		t.Fatalf("not routed deeply: %s", forward)
	}
	raw, err := os.ReadFile(statePath)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(raw, []byte("root cause")) || bytes.Contains(raw, []byte("input")) {
		t.Fatalf("prompt was persisted: %s", raw)
	}
}

func TestAutoTurnFailsClosedBeforeCatalogObservation(t *testing.T) {
	tr, _ := newFixtureTransformer(t)
	forward, immediate, err := tr.ClientLine([]byte(`{"id":7,"method":"turn/start","params":{"threadId":"t1","model":"athena-auto","input":[{"type":"text","text":"สรุปสั้น"}]}}`))
	if err != nil {
		t.Fatal(err)
	}
	if len(forward) != 0 || !bytes.Contains(immediate, []byte(`"code":-32072`)) {
		t.Fatalf("request did not fail closed: forward=%s immediate=%s", forward, immediate)
	}
}

func TestSecretaryTriggerInjectsVerifiedVoiceWithoutStoringPrompt(t *testing.T) {
	tr, statePath := newFixtureTransformer(t)
	seedCatalog(t, tr)
	forward, _, err := tr.ClientLine([]byte(`{"id":8,"method":"turn/start","params":{"threadId":"t2","model":"athena-auto","input":[{"type":"text","text":"อาเทน่า ตรวจโปรเจกต์นี้"}]}}`))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(forward, []byte(`"athena_voice_bootstrap"`)) || !bytes.Contains(forward, []byte(`"kind":"application"`)) || !bytes.Contains(forward, []byte(`"value":"ให้แทนตัวเองว่า ฉัน และลงท้ายว่า ค่ะ"`)) {
		t.Fatalf("voice context missing: %s", forward)
	}
	raw, err := os.ReadFile(statePath)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(raw, []byte("ตรวจโปรเจกต์นี้")) {
		t.Fatalf("secretary prompt persisted: %s", raw)
	}
}

func TestExistingDeepPhaseDoesNotDowngradeUntilNewTask(t *testing.T) {
	tr, _ := newFixtureTransformer(t)
	seedCatalog(t, tr)
	first, _, err := tr.ClientLine([]byte(`{"id":9,"method":"turn/start","params":{"threadId":"t3","model":"athena-auto","input":[{"type":"text","text":"วิเคราะห์ architecture"}]}}`))
	if err != nil || !bytes.Contains(first, []byte(`"model":"gpt-5.6-sol"`)) {
		t.Fatalf("first route: %s %v", first, err)
	}
	second, _, err := tr.ClientLine([]byte(`{"id":10,"method":"turn/start","params":{"threadId":"t3","input":[{"type":"text","text":"สรุปสั้น"}]}}`))
	if err != nil || !bytes.Contains(second, []byte(`"model":"gpt-5.6-sol"`)) {
		t.Fatalf("phase downgraded: %s %v", second, err)
	}
	third, _, err := tr.ClientLine([]byte(`{"id":11,"method":"turn/start","params":{"threadId":"t3","input":[{"type":"text","text":"เริ่มงานใหม่: สรุปสั้น"}]}}`))
	if err != nil || !bytes.Contains(third, []byte(`"model":"gpt-5.6-luna"`)) {
		t.Fatalf("new phase did not reset: %s %v", third, err)
	}
}

func TestMalformedJSONPassesThroughUnchanged(t *testing.T) {
	tr, _ := newFixtureTransformer(t)
	input := []byte("not-json")
	forward, immediate, err := tr.ClientLine(input)
	if err != nil || len(immediate) != 0 || !bytes.Equal(forward, input) {
		t.Fatalf("malformed line changed: %q %q %v", forward, immediate, err)
	}
}

func TestThreadStartResponsePreservesVirtualDisplayModel(t *testing.T) {
	tr, _ := newFixtureTransformer(t)
	seedCatalog(t, tr)
	_, immediate, err := tr.ClientLine([]byte(`{"id":20,"method":"thread/start","params":{"model":"athena-auto"}}`))
	if err != nil || len(immediate) != 0 {
		t.Fatalf("thread start request failed: immediate=%s err=%v", immediate, err)
	}
	response, err := tr.ServerLine([]byte(`{"id":20,"result":{"thread":{"id":"t20","model":"gpt-5.6-terra"},"model":"gpt-5.6-terra","reasoningEffort":"medium"}}`))
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Count(response, []byte(`"athena-auto"`)) != 2 || !bytes.Contains(response, []byte(`"reasoningEffort":"medium"`)) {
		t.Fatalf("virtual display was not preserved: %s", response)
	}
}

func TestServerNotificationsPreserveVirtualThreadSettings(t *testing.T) {
	tr, _ := newFixtureTransformer(t)
	seedCatalog(t, tr)
	_, _, _ = tr.ClientLine([]byte(`{"id":21,"method":"thread/start","params":{"model":"athena-auto"}}`))
	if _, err := tr.ServerLine([]byte(`{"id":21,"result":{"thread":{"id":"t21","model":"gpt-5.6-terra"}}}`)); err != nil {
		t.Fatal(err)
	}
	started, err := tr.ServerLine([]byte(`{"method":"thread/started","params":{"thread":{"id":"t21","model":"gpt-5.6-terra"}}}`))
	if err != nil || !bytes.Contains(started, []byte(`"model":"athena-auto"`)) {
		t.Fatalf("thread/started was not rewritten: %s %v", started, err)
	}
	updated, err := tr.ServerLine([]byte(`{"method":"thread/settings/updated","params":{"threadId":"t21","threadSettings":{"model":"gpt-5.6-terra","effort":"medium"}}}`))
	if err != nil || !bytes.Contains(updated, []byte(`"model":"athena-auto"`)) {
		t.Fatalf("thread/settings/updated was not rewritten: %s %v", updated, err)
	}
}

func TestThreadResumeRewritesVirtualModelBeforeForwarding(t *testing.T) {
	tr, _ := newFixtureTransformer(t)
	seedCatalog(t, tr)

	forward, immediate, err := tr.ClientLine([]byte(`{"id":30,"method":"thread/resume","params":{"threadId":"t30","model":"athena-auto"}}`))
	if err != nil {
		t.Fatal(err)
	}
	if len(immediate) != 0 {
		t.Fatalf("unexpected immediate response: %s", immediate)
	}
	if bytes.Contains(forward, []byte(`athena-auto`)) {
		t.Fatalf("virtual model escaped to real Codex: %s", forward)
	}
	if !bytes.Contains(forward, []byte(`"model":"gpt-5.6-terra"`)) {
		t.Fatalf("resume was not routed to an official model: %s", forward)
	}
}

func TestThreadForkRewritesVirtualModelAndTracksForkedThread(t *testing.T) {
	tr, _ := newFixtureTransformer(t)
	seedCatalog(t, tr)

	forward, immediate, err := tr.ClientLine([]byte(`{"id":31,"method":"thread/fork","params":{"threadId":"source","model":"athena-auto"}}`))
	if err != nil {
		t.Fatal(err)
	}
	if len(immediate) != 0 {
		t.Fatalf("unexpected immediate response: %s", immediate)
	}
	if bytes.Contains(forward, []byte(`athena-auto`)) {
		t.Fatalf("virtual model escaped to real Codex: %s", forward)
	}
	if !bytes.Contains(forward, []byte(`"model":"gpt-5.6-terra"`)) {
		t.Fatalf("fork was not routed to an official model: %s", forward)
	}

	response, err := tr.ServerLine([]byte(`{"id":31,"result":{"thread":{"id":"forked","model":"gpt-5.6-terra"},"model":"gpt-5.6-terra","reasoningEffort":"medium"}}`))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(response, []byte(`"model":"athena-auto"`)) {
		t.Fatalf("forked thread did not preserve Auto display state: %s", response)
	}
}

func TestUnknownRequestFailsClosedWhenVirtualModelWouldEscape(t *testing.T) {
	tr, _ := newFixtureTransformer(t)
	seedCatalog(t, tr)

	forward, immediate, err := tr.ClientLine([]byte(`{"id":32,"method":"future/thread/action","params":{"model":"athena-auto"}}`))
	if err != nil {
		t.Fatal(err)
	}
	if len(forward) != 0 {
		t.Fatalf("unsafe request was forwarded: %s", forward)
	}
	if !bytes.Contains(immediate, []byte(`"code":-32072`)) {
		t.Fatalf("unsafe request did not fail closed: %s", immediate)
	}
}
