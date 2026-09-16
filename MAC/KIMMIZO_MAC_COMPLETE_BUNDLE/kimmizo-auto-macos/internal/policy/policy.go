package policy

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
)

const SchemaVersion = 1

type Route struct {
	Tier             string `json:"tier"`
	Model            string `json:"model"`
	Effort           string `json:"effort"`
	RequiresApproval bool   `json:"requires_approval"`
}

type Catalog struct {
	Models       map[string][]string
	DefaultModel string
}

type RoutePolicy struct {
	Models           []string `json:"models"`
	Efforts          []string `json:"efforts"`
	RequiresApproval bool     `json:"requires_approval,omitempty"`
}

type Policy struct {
	SchemaVersion int                    `json:"schema_version"`
	PolicyVersion string                 `json:"policy_version"`
	Routes        map[string]RoutePolicy `json:"routes"`
}

type Voice struct {
	SchemaVersion int    `json:"schema_version"`
	PolicyVersion string `json:"policy_version"`
	Configured    bool   `json:"configured"`
	Name          string `json:"name"`
	Trigger       string `json:"trigger"`
	Language      string `json:"language"`
	Pronoun       string `json:"pronoun"`
	Ending        string `json:"ending"`
	Instruction   string `json:"instruction"`
	StoresPrompts bool   `json:"stores_prompts"`
}

func verifiedBytes(path, hashPath string) ([]byte, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	expectedText, err := os.ReadFile(hashPath)
	if err != nil {
		return nil, err
	}
	expected, err := hex.DecodeString(strings.TrimSpace(string(expectedText)))
	if err != nil || len(expected) != sha256.Size {
		return nil, errors.New("invalid SHA-256 sidecar")
	}
	actual := sha256.Sum256(raw)
	if subtle.ConstantTimeCompare(expected, actual[:]) != 1 {
		return nil, errors.New("SHA-256 mismatch")
	}
	return raw, nil
}

func LoadVerified(path, hashPath string) (Policy, error) {
	raw, err := verifiedBytes(path, hashPath)
	if err != nil {
		return Policy{}, fmt.Errorf("verify policy: %w", err)
	}
	var p Policy
	if err := json.Unmarshal(raw, &p); err != nil {
		return Policy{}, fmt.Errorf("parse policy: %w", err)
	}
	if p.SchemaVersion != SchemaVersion {
		return Policy{}, fmt.Errorf("unsupported policy schema %d", p.SchemaVersion)
	}
	if strings.TrimSpace(p.PolicyVersion) == "" {
		return Policy{}, errors.New("policy version is required")
	}
	for _, tier := range []string{"fast", "balanced", "deep", "critical", "ultra"} {
		route, ok := p.Routes[tier]
		if !ok || len(route.Models) == 0 || len(route.Efforts) == 0 {
			return Policy{}, fmt.Errorf("route %q is incomplete", tier)
		}
	}
	return p, nil
}

func LoadVoiceVerified(path, hashPath string) (Voice, error) {
	raw, err := verifiedBytes(path, hashPath)
	if err != nil {
		return Voice{}, fmt.Errorf("verify voice: %w", err)
	}
	var voice Voice
	if err := json.Unmarshal(raw, &voice); err != nil {
		return Voice{}, fmt.Errorf("parse voice: %w", err)
	}
	if voice.SchemaVersion != SchemaVersion {
		return Voice{}, fmt.Errorf("unsupported voice schema %d", voice.SchemaVersion)
	}
	if strings.TrimSpace(voice.Name) != "" || strings.TrimSpace(voice.Trigger) != "" {
		voice.Configured = true
	}
	if strings.TrimSpace(voice.PolicyVersion) == "" || voice.Language != "th" || voice.Pronoun != "ฉัน" || voice.Ending != "ค่ะ" || strings.TrimSpace(voice.Instruction) == "" || voice.StoresPrompts {
		return Voice{}, errors.New("voice contract mismatch")
	}
	if voice.Configured && (strings.TrimSpace(voice.Name) == "" || strings.TrimSpace(voice.Trigger) == "") {
		return Voice{}, errors.New("voice contract mismatch")
	}
	if !voice.Configured && (strings.TrimSpace(voice.Name) != "" || strings.TrimSpace(voice.Trigger) != "") {
		return Voice{}, errors.New("voice contract mismatch")
	}
	return voice, nil
}

func (p Policy) Choose(task string, catalog Catalog) (Route, error) {
	return p.choose(task, catalog, false)
}

func (p Policy) ChooseApproved(task string, catalog Catalog) (Route, error) {
	return p.choose(task, catalog, true)
}

func (p Policy) choose(task string, catalog Catalog, ultraApproved bool) (Route, error) {
	tier := Classify(task)
	rule, ok := p.Routes[tier]
	if !ok {
		return Route{}, fmt.Errorf("route %q is missing", tier)
	}
	if rule.RequiresApproval && !ultraApproved {
		return Route{Tier: tier, RequiresApproval: true}, nil
	}
	for _, model := range rule.Models {
		observedEfforts, present := catalog.Models[model]
		if !present {
			continue
		}
		for _, preferred := range rule.Efforts {
			if containsFold(observedEfforts, preferred) {
				return Route{Tier: tier, Model: model, Effort: preferred}, nil
			}
		}
	}
	return Route{}, fmt.Errorf("no verified model and reasoning effort for tier %q", tier)
}

func Classify(task string) string {
	text := strings.ToLower(strings.TrimSpace(task))
	if containsAny(text, []string{"หลายเอเจนต์", "multi-agent", "multi agent", "ทั้งโค้ดเบส", "whole codebase", "ultra"}) {
		return "ultra"
	}
	if containsAny(text, []string{"security", "ช่องโหว่", "ฐานข้อมูล", "database", "migration", "production", "deploy", "firewall", "ทำลาย", "destructive", "credential", "secret"}) {
		return "critical"
	}
	if containsAny(text, []string{"architecture", "root cause", "debug", "วิเคราะห์", "ออกแบบระบบ", "code review", "review code", "รีวิวโค้ด", "ซับซ้อน"}) {
		return "deep"
	}
	if containsAny(text, []string{"สรุป", "แปล", "สั้น", "ตรวจชื่อ", "list files", "อ่านไฟล์", "simple"}) {
		return "fast"
	}
	return "balanced"
}

func containsAny(text string, needles []string) bool {
	for _, needle := range needles {
		if strings.Contains(text, needle) {
			return true
		}
	}
	return false
}

func containsFold(values []string, target string) bool {
	for _, value := range values {
		if strings.EqualFold(value, target) {
			return true
		}
	}
	return false
}
