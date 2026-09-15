package app

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"

	"athena-auto/internal/policy"
	"athena-auto/internal/proxy"
	"athena-auto/internal/state"
)

const Version = "1.0.0"

type Status struct {
	Status               string `json:"status"`
	Version              string `json:"version"`
	VirtualModel         string `json:"virtualModel"`
	DisplayName          string `json:"displayName"`
	StoresPrompts        bool   `json:"storesPrompts"`
	SecretsCopied        bool   `json:"secretsCopied"`
	PolicyVerified       bool   `json:"policyVerified"`
	VoiceVerified        bool   `json:"voiceVerified"`
	RealCLIConfigured    bool   `json:"realCliConfigured"`
	RealCLIExecutable    bool   `json:"realCliExecutable"`
	DefaultAuto          bool   `json:"defaultAuto"`
	RouteCount           int    `json:"routeCount"`
	SecretaryThreadCount int    `json:"secretaryThreadCount"`
	HostOS               string `json:"hostOs"`
	HostArch             string `json:"hostArch"`
	PolicyError          string `json:"policyError,omitempty"`
	VoiceError           string `json:"voiceError,omitempty"`
	RealCLIError         string `json:"realCliError,omitempty"`
	StateError           string `json:"stateError,omitempty"`
}

type runtimeFiles struct {
	home       string
	policy     string
	policyHash string
	voice      string
	voiceHash  string
	state      string
	realPath   string
}

func Run(args []string, stdin io.Reader, stdout, stderr io.Writer, environ []string, executable string) int {
	files, err := locateRuntime(environ, executable)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "athena-auto: %v\n", err)
		return 78
	}

	if len(args) > 0 {
		switch args[0] {
		case "--athena-status", "--athena-self-test":
			status := inspect(files, executable)
			if args[0] == "--athena-self-test" && status.Status != "ready" {
				status.Status = "degraded"
			}
			if err := json.NewEncoder(stdout).Encode(status); err != nil {
				_, _ = fmt.Fprintf(stderr, "athena-auto: encode status: %v\n", err)
				return 74
			}
			if status.Status != "ready" {
				return 1
			}
			return 0
		case "--athena-default-auto-on", "--athena-default-auto-off":
			store, err := state.Load(files.state)
			if err != nil {
				_, _ = fmt.Fprintf(stderr, "athena-auto: load state: %v\n", err)
				return 1
			}
			enabled := args[0] == "--athena-default-auto-on"
			if err := store.SetDefaultAuto(enabled); err != nil {
				_, _ = fmt.Fprintf(stderr, "athena-auto: save default Auto: %v\n", err)
				return 1
			}
			_ = json.NewEncoder(stdout).Encode(map[string]any{"status": "ok", "defaultAuto": enabled})
			return 0
		}
	}

	realCLI, err := verifiedRealCLI(files.realPath, executable)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "athena-auto: %v\n", err)
		return 78
	}
	if len(args) > 0 && args[0] == "app-server" {
		loadedPolicy, err := policy.LoadVerified(files.policy, files.policyHash)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "athena-auto: %v\n", err)
			return 78
		}
		voice, err := policy.LoadVoiceVerified(files.voice, files.voiceHash)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "athena-auto: %v\n", err)
			return 78
		}
		if voice.PolicyVersion != loadedPolicy.PolicyVersion {
			_, _ = fmt.Fprintln(stderr, "athena-auto: policy and voice versions do not match")
			return 78
		}
		store, err := state.Load(files.state)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "athena-auto: load state: %v\n", err)
			return 78
		}
		transformer := proxy.NewTransformer(loadedPolicy, voice, store)
		return proxy.RunAppServer(context.Background(), realCLI, args, transformer, stdin, stdout, stderr, environ)
	}
	return proxy.RunChild(context.Background(), realCLI, args, stdin, stdout, stderr, environ)
}

func locateRuntime(environ []string, executable string) (runtimeFiles, error) {
	home := strings.TrimSpace(environmentValue(environ, "ATHENA_HOME"))
	if home == "" {
		if strings.TrimSpace(executable) == "" {
			return runtimeFiles{}, errors.New("cannot locate Athena executable")
		}
		absolute, err := filepath.Abs(executable)
		if err != nil {
			return runtimeFiles{}, fmt.Errorf("resolve Athena executable: %w", err)
		}
		home = filepath.Dir(absolute)
	}
	absoluteHome, err := filepath.Abs(home)
	if err != nil {
		return runtimeFiles{}, fmt.Errorf("resolve Athena home: %w", err)
	}
	return runtimeFiles{
		home:       absoluteHome,
		policy:     filepath.Join(absoluteHome, "model-policy.json"),
		policyHash: filepath.Join(absoluteHome, "model-policy.sha256"),
		voice:      filepath.Join(absoluteHome, "voice-bootstrap.json"),
		voiceHash:  filepath.Join(absoluteHome, "voice-bootstrap.sha256"),
		state:      filepath.Join(absoluteHome, "state.json"),
		realPath:   filepath.Join(absoluteHome, "real-codex.path"),
	}, nil
}

func inspect(files runtimeFiles, executable string) Status {
	status := Status{
		Status:        "ready",
		Version:       Version,
		VirtualModel:  proxy.VirtualModel,
		DisplayName:   proxy.VirtualDisplayName,
		StoresPrompts: false,
		SecretsCopied: false,
		HostOS:        runtime.GOOS,
		HostArch:      runtime.GOARCH,
	}
	loadedPolicy, policyErr := policy.LoadVerified(files.policy, files.policyHash)
	if policyErr != nil {
		status.Status = "degraded"
		status.PolicyError = policyErr.Error()
	} else {
		status.PolicyVerified = true
	}
	voice, voiceErr := policy.LoadVoiceVerified(files.voice, files.voiceHash)
	if voiceErr != nil {
		status.Status = "degraded"
		status.VoiceError = voiceErr.Error()
	} else if policyErr == nil && voice.PolicyVersion != loadedPolicy.PolicyVersion {
		status.Status = "degraded"
		status.VoiceError = "policy and voice versions do not match"
	} else {
		status.VoiceVerified = true
	}
	if raw, err := os.ReadFile(files.realPath); err == nil && strings.TrimSpace(string(raw)) != "" {
		status.RealCLIConfigured = true
	}
	if _, err := verifiedRealCLI(files.realPath, executable); err != nil {
		status.Status = "degraded"
		status.RealCLIError = err.Error()
	} else {
		status.RealCLIExecutable = true
	}
	store, err := state.Load(files.state)
	if err != nil {
		status.Status = "degraded"
		status.StateError = err.Error()
	} else {
		status.DefaultAuto, status.RouteCount, status.SecretaryThreadCount = store.Snapshot()
	}
	return status
}

func verifiedRealCLI(pathFile, executable string) (string, error) {
	raw, err := os.ReadFile(pathFile)
	if err != nil {
		return "", fmt.Errorf("read real Codex path: %w", err)
	}
	path := strings.TrimSpace(string(raw))
	if path == "" || !filepath.IsAbs(path) {
		return "", errors.New("real Codex path must be absolute")
	}
	info, err := os.Stat(path)
	if err != nil {
		return "", fmt.Errorf("inspect real Codex: %w", err)
	}
	if info.IsDir() || (!isExecutable(info) && runtime.GOOS != "windows") {
		return "", errors.New("real Codex path is not executable")
	}
	if samePath(path, executable) {
		return "", errors.New("real Codex path points back to Athena")
	}
	return path, nil
}

func isExecutable(info os.FileInfo) bool { return info.Mode().Perm()&0o111 != 0 }

func samePath(left, right string) bool {
	leftAbs, leftErr := filepath.Abs(left)
	rightAbs, rightErr := filepath.Abs(right)
	return leftErr == nil && rightErr == nil && strings.EqualFold(filepath.Clean(leftAbs), filepath.Clean(rightAbs))
}

func environmentValue(environ []string, name string) string {
	for index := len(environ) - 1; index >= 0; index-- {
		entry := environ[index]
		separator := strings.IndexByte(entry, '=')
		if separator > 0 && strings.EqualFold(entry[:separator], name) {
			return entry[separator+1:]
		}
	}
	return ""
}
