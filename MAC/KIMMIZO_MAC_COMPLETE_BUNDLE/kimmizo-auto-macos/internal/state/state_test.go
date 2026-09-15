package state

import (
	"bytes"
	"os"
	"path/filepath"
	"sync"
	"testing"

	"athena-auto/internal/policy"
)

func TestStateNeverSerializesPromptText(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.json")
	store, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := store.SetRoute("thread-1", policy.Route{Tier: "deep", Model: "gpt-5.6-sol", Effort: "high"}); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range [][]byte{[]byte("prompt"), []byte("taskText"), []byte("root cause")} {
		if bytes.Contains(raw, forbidden) {
			t.Fatalf("state contains forbidden prompt material %q: %s", forbidden, raw)
		}
	}
}

func TestStateRoundTripsRouteAndDefault(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.json")
	store, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	want := policy.Route{Tier: "critical", Model: "gpt-6-astra", Effort: "xhigh"}
	if err := store.SetRoute("thread-9", want); err != nil {
		t.Fatal(err)
	}
	if err := store.SetDefaultAuto(true); err != nil {
		t.Fatal(err)
	}
	reloaded, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	got, ok := reloaded.Route("thread-9")
	if !ok || got != want {
		t.Fatalf("route=%#v ok=%v", got, ok)
	}
	if !reloaded.DefaultAuto() {
		t.Fatal("default Auto did not round trip")
	}
}

func TestConcurrentWritesLeaveValidStateAndNoTempFiles(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "state.json")
	store, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	var wg sync.WaitGroup
	for i := 0; i < 12; i++ {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			if err := store.SetDefaultAuto(index%2 == 0); err != nil {
				t.Errorf("write: %v", err)
			}
		}(i)
	}
	wg.Wait()
	if _, err := Load(path); err != nil {
		t.Fatalf("final state invalid: %v", err)
	}
	matches, err := filepath.Glob(path + ".tmp-*")
	if err != nil {
		t.Fatal(err)
	}
	if len(matches) != 0 {
		t.Fatalf("temporary files remain: %v", matches)
	}
}

func TestEmptyThreadIDIsRejected(t *testing.T) {
	store, err := Load(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err := store.SetRoute("", policy.Route{Tier: "fast"}); err == nil {
		t.Fatal("empty thread id was accepted")
	}
}
