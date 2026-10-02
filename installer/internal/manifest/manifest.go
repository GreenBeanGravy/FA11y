// Package manifest describes everything Updater.exe installs besides
// FA11y's own files: the private Python, the pinned requirements, which
// repository paths to sync, and external components such as drivers.
//
// The manifest lives in the repository at installer/manifest.json, so
// adding a component (for example Npcap) is a data change, not a code change.
package manifest

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

// Path is the manifest's location inside the repository.
const Path = "installer/manifest.json"

const supportedSchema = 1

type Manifest struct {
	Schema       int         `json:"schema"`
	Repo         string      `json:"repo"`
	Branch       string      `json:"branch"`
	Python       Python      `json:"python"`
	Requirements string      `json:"requirements"`
	Sync         Sync        `json:"sync"`
	Components   []Component `json:"components"`
}

type Python struct {
	Version       string `json:"version"`
	URL           string `json:"url"`
	SHA256        string `json:"sha256"`
	ArchiveSubdir string `json:"archive_subdir"` // folder inside the archive holding python.exe
}

type Sync struct {
	// Exclude lists repository paths that are not installed. Entries ending
	// in "/" match a whole folder.
	Exclude []string `json:"exclude"`
	// AddOnly lists folders whose files are added when missing but never
	// overwritten or removed, so users can customize them.
	AddOnly []string `json:"add_only"`
}

type Component struct {
	ID       string   `json:"id"`
	Name     string   `json:"name"`
	Reason   string   `json:"reason"`
	Detect   Detect   `json:"detect"`
	Download Download `json:"download"`
	Install  Install  `json:"install"`
	Elevate  bool     `json:"elevate"`
}

// Detect says how to tell that a component is already installed. Every
// field that is set must match. Paths may use %VAR% environment variables
// and %FA11Y_FILES% for the FA11y Files folder.
type Detect struct {
	PathGlob             string `json:"path_glob,omitempty"`
	UninstallDisplayName string `json:"uninstall_display_name,omitempty"`
}

type Download struct {
	URL    string `json:"url"`
	SHA256 string `json:"sha256,omitempty"`
	SHA512 string `json:"sha512,omitempty"`
}

// Install says how to install a downloaded component.
//
//	msi:  msiexec /i <file> <args>
//	exe:  <file> <args>
//	file: copy to <dest> inside the FA11y Files folder
type Install struct {
	Type         string   `json:"type"`
	Args         []string `json:"args,omitempty"`
	Dest         string   `json:"dest,omitempty"`
	SuccessCodes []int    `json:"success_codes,omitempty"`
}

// RebootCodes are installer exit codes that mean success, restart needed.
var RebootCodes = map[int]bool{1641: true, 3010: true}

// Parse decodes and validates a manifest.
func Parse(data []byte) (*Manifest, error) {
	var m Manifest
	if err := json.Unmarshal(data, &m); err != nil {
		return nil, fmt.Errorf("manifest: %w", err)
	}
	if m.Schema != supportedSchema {
		return nil, fmt.Errorf("manifest schema %d is not supported by this updater (needs %d); download the latest Updater.exe", m.Schema, supportedSchema)
	}
	if m.Repo == "" || m.Branch == "" || m.Python.Version == "" || m.Python.URL == "" || m.Python.SHA256 == "" {
		return nil, fmt.Errorf("manifest: repo, branch and python fields are required")
	}
	seen := map[string]bool{}
	for _, c := range m.Components {
		if c.ID == "" || seen[c.ID] {
			return nil, fmt.Errorf("manifest: component ids must be unique and non-empty (%q)", c.ID)
		}
		seen[c.ID] = true
		if c.Detect == (Detect{}) {
			return nil, fmt.Errorf("manifest: component %s has no detect rule", c.ID)
		}
		if c.Download.SHA256 == "" && c.Download.SHA512 == "" {
			return nil, fmt.Errorf("manifest: component %s download has no hash", c.ID)
		}
		switch c.Install.Type {
		case "msi", "exe":
		case "file":
			if c.Install.Dest == "" || c.Elevate {
				return nil, fmt.Errorf("manifest: file component %s needs dest and no elevation", c.ID)
			}
		default:
			return nil, fmt.Errorf("manifest: component %s has unknown install type %q", c.ID, c.Install.Type)
		}
	}
	return &m, nil
}

// Load reads and parses a manifest file.
func Load(path string) (*Manifest, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return Parse(data)
}

// Excluded reports whether a repository path is not installed.
func (s Sync) Excluded(path string) bool { return matchAny(s.Exclude, path) }

// IsAddOnly reports whether a repository path is only ever added.
func (s Sync) IsAddOnly(path string) bool { return matchAny(s.AddOnly, path) }

func matchAny(patterns []string, path string) bool {
	for _, p := range patterns {
		if strings.HasSuffix(p, "/") {
			if strings.HasPrefix(path, p) {
				return true
			}
		} else if path == p {
			return true
		}
	}
	return false
}

// SuccessCode reports whether code means the installer succeeded.
func (i Install) SuccessCode(code int) bool {
	if len(i.SuccessCodes) == 0 {
		return code == 0
	}
	for _, c := range i.SuccessCodes {
		if c == code {
			return true
		}
	}
	return false
}
