package proxy

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"

	"athena-auto/internal/policy"
	"athena-auto/internal/state"
)

const (
	VirtualModel       = "athena-auto"
	VirtualDisplayName = "✦ Auto"
	VirtualDescription = "ปรับโมเดลตามช่วงงาน"
	codeVoiceInvalid   = -32071
	codeModelInvalid   = -32072
	codeContextInvalid = -32073
)

type pendingRequest struct {
	method         string
	firstModelPage bool
	autoStart      bool
	startRoute     policy.Route
}

type Transformer struct {
	policy policy.Policy
	voice  policy.Voice
	state  *state.Store

	mu      sync.Mutex
	pending map[string]pendingRequest
	catalog policy.Catalog
}

func NewTransformer(p policy.Policy, voice policy.Voice, store *state.Store) *Transformer {
	return &Transformer{
		policy:  p,
		voice:   voice,
		state:   store,
		pending: make(map[string]pendingRequest),
		catalog: policy.Catalog{Models: make(map[string][]string)},
	}
}

func (t *Transformer) ClientLine(line []byte) (forward, immediate []byte, err error) {
	var message map[string]any
	if json.Unmarshal(bytes.TrimPrefix(line, []byte{0xEF, 0xBB, 0xBF}), &message) != nil {
		return line, nil, nil
	}
	method, _ := message["method"].(string)
	params, _ := message["params"].(map[string]any)
	id, hasID := message["id"]
	changed := false
	var pending *pendingRequest

	switch method {
	case "model/list":
		_, hasCursor := params["cursor"]
		value := pendingRequest{method: method, firstModelPage: params == nil || !hasCursor || params["cursor"] == nil}
		pending = &value
	case "config/read":
		value := pendingRequest{method: method}
		pending = &value
	case "config/value/write":
		if params != nil {
			var blocked []byte
			changed, blocked = t.handleConfigWrite(params, id)
			if blocked != nil {
				return nil, blocked, nil
			}
		}
		value := pendingRequest{method: method}
		pending = &value
	case "config/batchWrite":
		if params != nil {
			if edits, ok := params["edits"].([]any); ok {
				for _, rawEdit := range edits {
					if edit, ok := rawEdit.(map[string]any); ok {
						editChanged, blocked := t.handleConfigWrite(edit, id)
						if blocked != nil {
							return nil, blocked, nil
						}
						changed = editChanged || changed
					}
				}
			}
		}
		value := pendingRequest{method: method}
		pending = &value
	case "thread/start":
		if params != nil {
			requested, _ := params["model"].(string)
			auto := isVirtual(requested) || (strings.TrimSpace(requested) == "" && t.state.DefaultAuto())
			value := pendingRequest{method: method, autoStart: auto}
			if auto {
				route, routeErr := t.chooseAdaptive("", "")
				if routeErr != nil {
					return nil, rpcError(id, codeModelInvalid, "ยังตรวจสอบ Model จาก Catalog ของ Codex ไม่สำเร็จ จึงไม่เริ่มงานค่ะ"), nil
				}
				params["model"] = route.Model
				config, _ := params["config"].(map[string]any)
				if config == nil {
					config = make(map[string]any)
					params["config"] = config
				}
				config["model_reasoning_effort"] = route.Effort
				value.startRoute = route
				changed = true
			}
			pending = &value
		}
	case "thread/settings/update":
		if params != nil {
			threadID := stringValue(params["threadId"])
			if rawModel, exists := params["model"]; exists {
				requested := stringValue(rawModel)
				if isVirtual(requested) {
					route, routeErr := t.chooseAdaptive(threadID, "")
					if routeErr != nil {
						return nil, rpcError(id, codeModelInvalid, "ยังตรวจสอบ Model จาก Catalog ของ Codex ไม่สำเร็จ จึงไม่เริ่มงานค่ะ"), nil
					}
					if err := t.state.SetRoute(threadID, route); err != nil {
						return nil, nil, err
					}
					params["model"] = route.Model
					params["effort"] = route.Effort
					rewriteCollaboration(params, route)
					changed = true
				}
			}
		}
		value := pendingRequest{method: method}
		pending = &value
	case "turn/start":
		if params != nil {
			threadID := stringValue(params["threadId"])
			auto := isVirtual(stringValue(params["model"])) || t.state.IsAuto(threadID)
			if auto {
				taskText := extractTaskText(params["input"])
				secretary := t.state.IsSecretary(threadID) || strings.Contains(strings.ToLower(taskText), strings.ToLower(t.voice.Trigger))
				if secretary {
					if !t.injectVoice(params) {
						return nil, rpcError(id, codeVoiceInvalid, "ยังตรวจสอบ voice bootstrap ของอาเทน่าไม่สำเร็จ จึงไม่เริ่มงานค่ะ"), nil
					}
					if err := t.state.SetSecretary(threadID, true); err != nil {
						return nil, nil, err
					}
					changed = true
				}

				approved := isUltraApproval(taskText) && t.state.ConsumeUltraApproval(threadID)
				if isUltraDenial(taskText) {
					_ = t.state.SetUltraApproval(threadID, false)
					approved = false
				}
				route, routeErr := t.chooseTurnRoute(threadID, taskText, approved)
				if routeErr != nil {
					return nil, rpcError(id, codeModelInvalid, "ยังตรวจสอบ Model จาก Catalog ของ Codex ไม่สำเร็จ จึงไม่เริ่มงานค่ะ"), nil
				}
				if route.RequiresApproval {
					if !t.injectUltraApproval(params) {
						return nil, rpcError(id, codeContextInvalid, "additionalContext ของงาน Ultra ไม่อยู่ในรูปแบบที่ปลอดภัย จึงไม่เริ่มงานค่ะ"), nil
					}
					if err := t.state.SetUltraApproval(threadID, true); err != nil {
						return nil, nil, err
					}
					route, routeErr = t.policy.Choose("วิเคราะห์ architecture", t.catalogSnapshot())
					if routeErr != nil {
						return nil, rpcError(id, codeModelInvalid, "ยังตรวจสอบ Model จาก Catalog ของ Codex ไม่สำเร็จ จึงไม่เริ่มงานค่ะ"), nil
					}
					changed = true
				}
				if err := t.state.SetRoute(threadID, route); err != nil {
					return nil, nil, err
				}
				params["model"] = route.Model
				params["effort"] = route.Effort
				rewriteCollaboration(params, route)
				changed = true
			}
		}
		value := pendingRequest{method: method}
		pending = &value
	case "thread/read", "thread/list", "thread/resume":
		value := pendingRequest{method: method}
		pending = &value
	}

	if pending != nil && hasID {
		t.mu.Lock()
		t.pending[idKey(id)] = *pending
		t.mu.Unlock()
	}
	if !changed {
		return line, nil, nil
	}
	encoded, err := json.Marshal(message)
	return encoded, nil, err
}

func (t *Transformer) ServerLine(line []byte) ([]byte, error) {
	var message map[string]any
	if json.Unmarshal(line, &message) != nil {
		return line, nil
	}
	pending := pendingRequest{}
	found := false
	if id, ok := message["id"]; ok {
		key := idKey(id)
		t.mu.Lock()
		pending, found = t.pending[key]
		delete(t.pending, key)
		t.mu.Unlock()
	}
	result, _ := message["result"].(map[string]any)
	changed := false
	if found && result != nil {
		switch pending.method {
		case "model/list":
			if pending.firstModelPage {
				changed = t.addAutoModel(result)
			}
		case "config/read":
			if t.state.DefaultAuto() {
				if config, ok := result["config"].(map[string]any); ok {
					config["model"] = VirtualModel
					changed = true
				}
			}
		case "thread/start":
			if pending.autoStart {
				if thread, ok := result["thread"].(map[string]any); ok {
					threadID := stringValue(thread["id"])
					if threadID != "" {
						if err := t.state.SetRoute(threadID, pending.startRoute); err != nil {
							return nil, err
						}
						changed = t.rewriteThreadResult(result, threadID) || changed
					}
				}
			}
		case "thread/read", "thread/resume":
			if thread, ok := result["thread"].(map[string]any); ok {
				changed = t.rewriteThreadResult(result, stringValue(thread["id"]))
			}
		case "thread/list":
			if data, ok := result["data"].([]any); ok {
				for _, item := range data {
					if thread, ok := item.(map[string]any); ok {
						changed = t.rewriteThread(thread) || changed
					}
				}
			}
		}
	}
	method := stringValue(message["method"])
	params, _ := message["params"].(map[string]any)
	if method == "thread/started" && params != nil {
		if thread, ok := params["thread"].(map[string]any); ok {
			changed = t.rewriteThread(thread) || changed
		}
	} else if method == "thread/settings/updated" && params != nil {
		threadID := stringValue(params["threadId"])
		if t.state.IsAuto(threadID) {
			if settings, ok := params["threadSettings"].(map[string]any); ok {
				settings["model"] = VirtualModel
				if route, found := t.state.Route(threadID); found {
					settings["effort"] = route.Effort
				}
				changed = true
			}
		}
	}
	if !changed {
		return line, nil
	}
	return json.Marshal(message)
}

func (t *Transformer) handleConfigWrite(edit map[string]any, id any) (bool, []byte) {
	if !strings.EqualFold(stringValue(edit["keyPath"]), "model") {
		return false, nil
	}
	value := stringValue(edit["value"])
	if isVirtual(value) {
		route, err := t.policy.Choose("", t.catalogSnapshot())
		if err != nil {
			return false, rpcError(id, codeModelInvalid, "ยังตรวจสอบ Model จาก Catalog ของ Codex ไม่สำเร็จ จึงไม่เริ่มงานค่ะ")
		}
		if err := t.state.SetDefaultAuto(true); err != nil {
			return false, rpcError(id, codeModelInvalid, "ไม่สามารถบันทึกค่า Auto ได้ค่ะ")
		}
		edit["value"] = route.Model
		return true, nil
	}
	if strings.TrimSpace(value) != "" {
		_ = t.state.SetDefaultAuto(false)
	}
	return false, nil
}

func (t *Transformer) addAutoModel(result map[string]any) bool {
	data, ok := result["data"].([]any)
	if !ok {
		return false
	}
	models := make([]any, 0, len(data)+1)
	observed := make(map[string][]string)
	var template map[string]any
	defaultModel := ""
	for _, item := range data {
		model, ok := item.(map[string]any)
		if !ok {
			models = append(models, item)
			continue
		}
		modelID := stringValue(model["model"])
		if modelID == "" {
			modelID = stringValue(model["id"])
		}
		if isVirtual(modelID) {
			continue
		}
		if modelID != "" {
			observed[modelID] = extractEfforts(model["supportedReasoningEfforts"])
			if isTrue(model["isDefault"]) {
				defaultModel = modelID
			}
			if template == nil || modelID == "gpt-5.6-sol" {
				template = model
			}
		}
		models = append(models, model)
	}
	if template == nil || len(observed) == 0 {
		return false
	}
	t.mu.Lock()
	t.catalog = policy.Catalog{Models: observed, DefaultModel: defaultModel}
	t.mu.Unlock()
	auto := cloneMap(template)
	auto["id"] = VirtualModel
	auto["model"] = VirtualModel
	auto["displayName"] = VirtualDisplayName
	auto["description"] = VirtualDescription
	auto["hidden"] = false
	auto["isDefault"] = t.state.DefaultAuto()
	auto["availabilityNux"] = map[string]any{"message": VirtualDescription}
	auto["defaultReasoningEffort"] = "medium"
	if t.state.DefaultAuto() {
		for _, item := range models {
			if model, ok := item.(map[string]any); ok {
				model["isDefault"] = false
			}
		}
	}
	result["data"] = append([]any{auto}, models...)
	return true
}

func (t *Transformer) chooseTurnRoute(threadID, task string, ultraApproved bool) (policy.Route, error) {
	catalog := t.catalogSnapshot()
	var candidate policy.Route
	var err error
	if ultraApproved {
		candidate, err = t.policy.ChooseApproved("หลายเอเจนต์ "+task, catalog)
	} else {
		candidate, err = t.policy.Choose(task, catalog)
	}
	if err != nil {
		return policy.Route{}, err
	}
	current, hasCurrent := t.state.Route(threadID)
	if candidate.RequiresApproval || !hasCurrent || isNewTask(task) || routeRank(candidate) > routeRank(current) {
		return candidate, nil
	}
	return current, nil
}

func (t *Transformer) chooseAdaptive(threadID, task string) (policy.Route, error) {
	candidate, err := t.policy.Choose(task, t.catalogSnapshot())
	if err != nil {
		return policy.Route{}, err
	}
	current, ok := t.state.Route(threadID)
	if !ok || isNewTask(task) || routeRank(candidate) > routeRank(current) {
		return candidate, nil
	}
	return current, nil
}

func (t *Transformer) catalogSnapshot() policy.Catalog {
	t.mu.Lock()
	defer t.mu.Unlock()
	copyModels := make(map[string][]string, len(t.catalog.Models))
	for model, efforts := range t.catalog.Models {
		copyModels[model] = append([]string(nil), efforts...)
	}
	return policy.Catalog{Models: copyModels, DefaultModel: t.catalog.DefaultModel}
}

func (t *Transformer) injectVoice(params map[string]any) bool {
	context, exists := params["additionalContext"]
	if exists && context != nil {
		if _, ok := context.(map[string]any); !ok {
			return false
		}
	}
	object, _ := context.(map[string]any)
	if object == nil {
		object = make(map[string]any)
	}
	object["athena_voice_bootstrap"] = map[string]any{
		"kind":  "application",
		"value": t.voice.Instruction,
	}
	params["additionalContext"] = object
	return true
}

func (t *Transformer) injectUltraApproval(params map[string]any) bool {
	context, exists := params["additionalContext"]
	if exists && context != nil {
		if _, ok := context.(map[string]any); !ok {
			return false
		}
	}
	object, _ := context.(map[string]any)
	if object == nil {
		object = make(map[string]any)
	}
	object["athena_auto_ultra_approval"] = map[string]any{
		"kind":  "application",
		"value": "งานนี้อาจเหมาะกับ Ultra แต่ยังไม่ได้รับอนุมัติ ห้ามเริ่มงานสาระสำคัญ ให้ถามผู้ใช้เป็นภาษาไทยก่อนว่าอนุมัติให้ใช้ Ultra หรือไม่ พร้อมบอกเหตุผลสั้น ๆ ค่ะ",
	}
	params["additionalContext"] = object
	return true
}

func (t *Transformer) rewriteThread(thread map[string]any) bool {
	threadID := stringValue(thread["id"])
	if !t.state.IsAuto(threadID) {
		return false
	}
	thread["model"] = VirtualModel
	return true
}

func (t *Transformer) rewriteThreadResult(result map[string]any, threadID string) bool {
	if !t.state.IsAuto(threadID) {
		return false
	}
	changed := false
	if thread, ok := result["thread"].(map[string]any); ok {
		changed = t.rewriteThread(thread) || changed
	}
	if _, exists := result["model"]; exists {
		result["model"] = VirtualModel
		changed = true
	}
	if route, found := t.state.Route(threadID); found {
		if _, exists := result["reasoningEffort"]; exists {
			result["reasoningEffort"] = route.Effort
			changed = true
		}
	}
	return changed
}

func rewriteCollaboration(params map[string]any, route policy.Route) {
	collaboration, _ := params["collaborationMode"].(map[string]any)
	settings, _ := collaboration["settings"].(map[string]any)
	if settings != nil {
		settings["model"] = route.Model
		settings["reasoning_effort"] = route.Effort
	}
}

func extractTaskText(input any) string {
	parts, ok := input.([]any)
	if !ok {
		return ""
	}
	var text []string
	for _, rawPart := range parts {
		part, ok := rawPart.(map[string]any)
		if ok && stringValue(part["type"]) == "text" {
			text = append(text, stringValue(part["text"]))
		}
	}
	return strings.Join(text, "\n")
}

func extractEfforts(value any) []string {
	items, ok := value.([]any)
	if !ok {
		return nil
	}
	var efforts []string
	for _, item := range items {
		switch typed := item.(type) {
		case string:
			efforts = append(efforts, typed)
		case map[string]any:
			if effort := stringValue(typed["reasoningEffort"]); effort != "" {
				efforts = append(efforts, effort)
			}
		}
	}
	return efforts
}

func cloneMap(source map[string]any) map[string]any {
	result := make(map[string]any, len(source))
	for key, value := range source {
		result[key] = value
	}
	return result
}

func routeRank(route policy.Route) int {
	return map[string]int{"fast": 1, "balanced": 2, "deep": 3, "critical": 4, "ultra": 5}[route.Tier]
}

func isNewTask(text string) bool {
	lower := strings.ToLower(text)
	return strings.Contains(lower, "เริ่มงานใหม่") || strings.Contains(lower, "งานใหม่:") || strings.Contains(lower, "new task:") || strings.Contains(lower, "reset auto")
}

func isUltraApproval(text string) bool {
	normalized := strings.TrimSpace(strings.ToLower(text))
	return normalized == "อนุมัติ" || normalized == "approved" || normalized == "approve" || normalized == "ยืนยัน"
}

func isUltraDenial(text string) bool {
	normalized := strings.TrimSpace(strings.ToLower(text))
	return normalized == "ไม่อนุมัติ" || normalized == "ปฏิเสธ" || normalized == "deny" || normalized == "cancel"
}

func isVirtual(model string) bool { return strings.EqualFold(strings.TrimSpace(model), VirtualModel) }
func isTrue(value any) bool       { typed, ok := value.(bool); return ok && typed }

func stringValue(value any) string {
	if value == nil {
		return ""
	}
	if text, ok := value.(string); ok {
		return text
	}
	return fmt.Sprint(value)
}

func idKey(id any) string {
	raw, _ := json.Marshal(id)
	return string(raw)
}

func rpcError(id any, code int, message string) []byte {
	response := map[string]any{"id": id, "error": map[string]any{"code": code, "message": message}}
	raw, _ := json.Marshal(response)
	return raw
}

var errLineTooLarge = errors.New("JSON-RPC line exceeds safety limit")
