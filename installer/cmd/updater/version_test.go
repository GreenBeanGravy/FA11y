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

func TestFixLauncherName(t *testing.T) {
	dir := t.TempDir()
	l := layout.New(dir)
	downloaded := filepath.Join(dir, "FA11y.Launcher.exe")
	if err := os.WriteFile(downloaded, []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	fixLauncherName(l)
	if _, err := os.Stat(l.Launcher()); err != nil {
		t.Fatalf("launcher not renamed: %v", err)
	}
	if _, err := os.Stat(downloaded); !os.IsNotExist(err) {
		t.Fatalf("downloaded name still there")
	}
}
