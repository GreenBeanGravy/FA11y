package main

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/GreenBeanGravy/FA11y/installer/internal/layout"
)

func TestVersionNewer(t *testing.T) {
	cases := []struct {
		remote, local string
		want          bool
	}{
		{"18.11.17", "18.11.16", true},
		{"18.11.16", "18.11.17", false},
		{"18.11.17", "18.11.17", false},
		{"19.0.0-beta.1", "18.11.17", true},
		{"19.0.0-beta.2", "19.0.0-beta.1", true},
		{"19.0.0-beta.1", "19.0.0-beta.1", false},
		{"19.0.0", "19.0.0-beta.3", true},
		{"19.0.0-beta.3", "19.0.0", false},
		{"18.11.17", "", true},
	}
	for _, c := range cases {
		if got := versionNewer(c.remote, c.local); got != c.want {
			t.Errorf("versionNewer(%q, %q) = %v, want %v", c.remote, c.local, got, c.want)
		}
	}
}

func TestRenameOldLauncher(t *testing.T) {
	for _, name := range layout.LegacyLauncherExes {
		dir := t.TempDir()
		l := layout.New(dir)
		old := filepath.Join(dir, name)
		if err := os.WriteFile(old, []byte("x"), 0o644); err != nil {
			t.Fatal(err)
		}
		if !renameOldLauncher(l) {
			t.Errorf("%s: not reported as renamed", name)
		}
		if _, err := os.Stat(l.Launcher()); err != nil {
			t.Errorf("%s: not renamed to %s: %v", name, layout.LauncherExe, err)
		}
		if _, err := os.Stat(old); !os.IsNotExist(err) {
			t.Errorf("%s: old name still there", name)
		}
	}
}

func TestRenameOldLauncherKeepsTheCurrentOne(t *testing.T) {
	dir := t.TempDir()
	l := layout.New(dir)
	os.WriteFile(l.Launcher(), []byte("new"), 0o644)
	old := filepath.Join(dir, layout.LegacyLauncherExes[0])
	os.WriteFile(old, []byte("old"), 0o644)
	if renameOldLauncher(l) {
		t.Error("reported a rename with the current launcher already there")
	}
	if data, _ := os.ReadFile(l.Launcher()); string(data) != "new" {
		t.Errorf("current launcher replaced: %q", data)
	}
	if _, err := os.Stat(old); !os.IsNotExist(err) {
		t.Error("old launcher not removed")
	}
}
