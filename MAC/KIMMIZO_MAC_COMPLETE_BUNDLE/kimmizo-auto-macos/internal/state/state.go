package state

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	"athena-auto/internal/policy"
)

const schemaVersion = 1

type diskState struct {
	SchemaVersion    int                     `json:"schema_version"`
	DefaultAuto      bool                    `json:"default_auto"`
	Routes           map[string]policy.Route `json:"routes"`
	SecretaryThreads map[string]bool         `json:"secretary_threads,omitempty"`
	UltraApprovals   map[string]bool         `json:"ultra_approvals,omitempty"`
	UpdatedAt        string                  `json:"updated_at"`
}

type Store struct {
	mu   sync.RWMutex
	path string
	data diskState
}

func Load(path string) (*Store, error) {
	if strings.TrimSpace(path) == "" {
		return nil, errors.New("state path is required")
	}
	store := &Store{path: path, data: newDiskState()}
	raw, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return store, nil
	}
	if err != nil {
		return nil, fmt.Errorf("read state: %w", err)
	}
	if err := json.Unmarshal(raw, &store.data); err != nil {
		return nil, fmt.Errorf("parse state: %w", err)
	}
	if store.data.SchemaVersion != schemaVersion {
		return nil, fmt.Errorf("unsupported state schema %d", store.data.SchemaVersion)
	}
	store.normalize()
	return store, nil
}

func newDiskState() diskState {
	return diskState{
		SchemaVersion:    schemaVersion,
		Routes:           make(map[string]policy.Route),
		SecretaryThreads: make(map[string]bool),
		UltraApprovals:   make(map[string]bool),
	}
}

func (s *Store) normalize() {
	if s.data.Routes == nil {
		s.data.Routes = make(map[string]policy.Route)
	}
	if s.data.SecretaryThreads == nil {
		s.data.SecretaryThreads = make(map[string]bool)
	}
	if s.data.UltraApprovals == nil {
		s.data.UltraApprovals = make(map[string]bool)
	}
}

func (s *Store) SetRoute(threadID string, route policy.Route) error {
	threadID = strings.TrimSpace(threadID)
	if threadID == "" {
		return errors.New("thread id is required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.data.Routes[threadID] = route
	return s.saveLocked()
}

func (s *Store) Route(threadID string) (policy.Route, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	route, ok := s.data.Routes[threadID]
	return route, ok
}

func (s *Store) IsAuto(threadID string) bool {
	_, ok := s.Route(threadID)
	return ok
}

func (s *Store) SetDefaultAuto(enabled bool) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.data.DefaultAuto = enabled
	return s.saveLocked()
}

func (s *Store) DefaultAuto() bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.data.DefaultAuto
}

func (s *Store) SetSecretary(threadID string, enabled bool) error {
	threadID = strings.TrimSpace(threadID)
	if threadID == "" {
		return errors.New("thread id is required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if enabled {
		s.data.SecretaryThreads[threadID] = true
	} else {
		delete(s.data.SecretaryThreads, threadID)
	}
	return s.saveLocked()
}

func (s *Store) IsSecretary(threadID string) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.data.SecretaryThreads[threadID]
}

func (s *Store) SetUltraApproval(threadID string, approved bool) error {
	threadID = strings.TrimSpace(threadID)
	if threadID == "" {
		return errors.New("thread id is required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if approved {
		s.data.UltraApprovals[threadID] = true
	} else {
		delete(s.data.UltraApprovals, threadID)
	}
	return s.saveLocked()
}

func (s *Store) ConsumeUltraApproval(threadID string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	approved := s.data.UltraApprovals[threadID]
	if approved {
		delete(s.data.UltraApprovals, threadID)
		_ = s.saveLocked()
	}
	return approved
}

func (s *Store) Snapshot() (defaultAuto bool, routeCount, secretaryCount int) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.data.DefaultAuto, len(s.data.Routes), len(s.data.SecretaryThreads)
}

func (s *Store) saveLocked() error {
	s.data.UpdatedAt = time.Now().UTC().Format(time.RFC3339Nano)
	raw, err := json.MarshalIndent(s.data, "", "  ")
	if err != nil {
		return fmt.Errorf("encode state: %w", err)
	}
	dir := filepath.Dir(s.path)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return fmt.Errorf("create state directory: %w", err)
	}
	temporary := fmt.Sprintf("%s.tmp-%d", s.path, os.Getpid())
	file, err := os.OpenFile(temporary, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o600)
	if err != nil {
		return fmt.Errorf("create temporary state: %w", err)
	}
	cleanup := true
	defer func() {
		if cleanup {
			_ = os.Remove(temporary)
		}
	}()
	if _, err := file.Write(append(raw, '\n')); err != nil {
		_ = file.Close()
		return fmt.Errorf("write temporary state: %w", err)
	}
	if err := file.Sync(); err != nil {
		_ = file.Close()
		return fmt.Errorf("sync temporary state: %w", err)
	}
	if err := file.Close(); err != nil {
		return fmt.Errorf("close temporary state: %w", err)
	}
	if err := os.Rename(temporary, s.path); err != nil {
		if runtime.GOOS != "windows" {
			return fmt.Errorf("replace state: %w", err)
		}
		if removeErr := os.Remove(s.path); removeErr != nil && !errors.Is(removeErr, os.ErrNotExist) {
			return fmt.Errorf("remove prior state: %w", removeErr)
		}
		if renameErr := os.Rename(temporary, s.path); renameErr != nil {
			return fmt.Errorf("replace state: %w", renameErr)
		}
	}
	cleanup = false
	return nil
}
