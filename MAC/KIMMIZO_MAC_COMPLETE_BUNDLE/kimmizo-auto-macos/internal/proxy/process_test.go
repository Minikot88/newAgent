package proxy

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"os"
	"strings"
	"testing"
)

func TestHelperChild(t *testing.T) {
	if os.Getenv("ATHENA_HELPER_CHILD") != "1" {
		return
	}
	if os.Getenv("ATHENA_HELPER_MODE") == "app-server" {
		_, _ = io.ReadAll(os.Stdin)
		_, _ = os.Stdout.WriteString(`{"id":1,"result":{"data":[{"id":"gpt-5.6-luna","model":"gpt-5.6-luna","supportedReasoningEfforts":["low","medium"],"isDefault":true},{"id":"gpt-5.6-terra","model":"gpt-5.6-terra","supportedReasoningEfforts":["medium","high"]}]}}` + "\n")
		return
	}
	observed := map[string]string{
		"CODEX_CLI_PATH": os.Getenv("CODEX_CLI_PATH"),
		"KEEP_ME":        os.Getenv("KEEP_ME"),
	}
	_ = json.NewEncoder(os.Stdout).Encode(observed)
	os.Exit(23)
}

func TestRunAppServerTransformsBothDirections(t *testing.T) {
	transformer, _ := newFixtureTransformer(t)
	input := strings.NewReader(`{"id":1,"method":"model/list","params":{}}` + "\n")
	var stdout, stderr bytes.Buffer
	environ := append(os.Environ(), "ATHENA_HELPER_CHILD=1", "ATHENA_HELPER_MODE=app-server")
	code := RunAppServer(
		context.Background(),
		os.Args[0],
		[]string{"-test.run=TestHelperChild"},
		transformer,
		input,
		&stdout,
		&stderr,
		environ,
	)
	if code != 0 {
		t.Fatalf("exit=%d stderr=%s", code, stderr.String())
	}
	if !strings.Contains(stdout.String(), `"model":"athena-auto"`) || !strings.Contains(stdout.String(), `"displayName":"✦ Auto"`) {
		t.Fatalf("server response was not transformed: %s", stdout.String())
	}
}

func TestRunChildRemovesCodexCLIPathAndPropagatesExit(t *testing.T) {
	var stdout, stderr bytes.Buffer
	environ := append(os.Environ(),
		"ATHENA_HELPER_CHILD=1",
		"CODEX_CLI_PATH=/tmp/athena-auto",
		"KEEP_ME=present",
	)
	code := RunChild(context.Background(), os.Args[0], []string{"-test.run=TestHelperChild"}, nil, &stdout, &stderr, environ)
	if code != 23 {
		t.Fatalf("exit=%d stderr=%s", code, stderr.String())
	}
	var observed map[string]string
	if err := json.Unmarshal(stdout.Bytes(), &observed); err != nil {
		t.Fatalf("decode helper output: %v (%q)", err, stdout.String())
	}
	if observed["CODEX_CLI_PATH"] != "" {
		t.Fatalf("recursive environment leaked: %q", observed["CODEX_CLI_PATH"])
	}
	if observed["KEEP_ME"] != "present" {
		t.Fatalf("unrelated environment was dropped: %#v", observed)
	}
}

func TestFilterChildEnvironmentIsCaseInsensitive(t *testing.T) {
	got := FilterChildEnvironment([]string{
		"Path=/usr/bin",
		"CODEX_CLI_PATH=/one",
		"codex_cli_path=/two",
		"ATHENA_REAL_CODEX=/real/codex",
		"SAFE=value",
	})
	joined := strings.Join(got, "\n")
	if strings.Contains(strings.ToLower(joined), "codex_cli_path=") {
		t.Fatalf("recursive environment remains: %q", joined)
	}
	if strings.Contains(strings.ToLower(joined), "athena_real_codex=") {
		t.Fatalf("private launcher environment remains: %q", joined)
	}
	if !strings.Contains(joined, "SAFE=value") || !strings.Contains(joined, "Path=/usr/bin") {
		t.Fatalf("safe environment missing: %q", joined)
	}
}
