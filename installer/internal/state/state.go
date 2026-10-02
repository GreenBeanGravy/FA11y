// Package state records what Updater.exe installed, so later runs can tell
// what changed and remove only files they put there.
package state

import (
	"encoding/json"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
)

// FileName is the state file inside the FA11y Files folder.
const FileName = ".fa11y-install.json"

type State struct {
	// Files maps each installed repository path to its git blob SHA.
	Files map[string]string `json:"files"`
	// LockSHA256 is the hash of the requirements lock last installed into the venv.
	LockSHA256 string `json:"lock_sha256,omitempty"`
	// Declined lists components the user declined to install (UAC refused).
	// Quick update checks do not ask for them again; a full update does.
	Declined []string `json:"declined,omitempty"`
}

func path(filesDir string) string { return filepath.Join(filesDir, FileName) }

// Load reads the state, returning an empty state when none exists yet.
func Load(filesDir string) (*State, error) {
	s := &State{Files: map[string]string{}}
	data, err := os.ReadFile(path(filesDir))
	if errors.Is(err, fs.ErrNotExist) {
		return s, nil
	}
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(data, s); err != nil {
		return nil, err
	}
	if s.Files == nil {
		s.Files = map[string]string{}
	}
	return s, nil
}

// Save writes the state atomically.
func (s *State) Save(filesDir string) error {
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	tmp := path(filesDir) + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path(filesDir))
}

func (s *State) IsDeclined(id string) bool {
	for _, d := range s.Declined {
		if d == id {
			return true
		}
	}
	return false
}

func (s *State) SetDeclined(id string, declined bool) {
	kept := s.Declined[:0]
	for _, d := range s.Declined {
		if d != id {
			kept = append(kept, d)
		}
	}
	if declined {
		kept = append(kept, id)
	}
	s.Declined = kept
}
