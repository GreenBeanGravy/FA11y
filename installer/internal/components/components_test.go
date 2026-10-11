package components

import (
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"testing"

	"github.com/GreenBeanGravy/FA11y/installer/internal/manifest"
)

func TestFileSHA256MakesAnOldCopyCountAsMissing(t *testing.T) {
	dir := t.TempDir()
	exe := filepath.Join(dir, "legendary.exe")
	os.WriteFile(exe, []byte("0.20.34"), 0o755)
	newHash := "0000000000000000000000000000000000000000000000000000000000000000"
	c := manifest.Component{ID: "legendary", Detect: manifest.Detect{PathGlob: `%FA11Y_FILES%\legendary.exe`}}
	if !Installed(c, dir) {
		t.Fatal("present file without a pinned hash should count as installed")
	}
	c.Detect.FileSHA256 = newHash
	if Installed(c, dir) {
		t.Error("an old legendary.exe counted as the pinned version")
	}
	// What install(file) leaves behind matches its own pin.
	src := filepath.Join(t.TempDir(), "download.exe")
	os.WriteFile(src, []byte("0.21.1"), 0o755)
	c.Download = manifest.Download{SHA256: sha256Hex(t, src)}
	c.Detect.FileSHA256 = c.Download.SHA256
	c.Install = manifest.Install{Type: "file", Dest: "legendary.exe"}
	if out := Install(c, src, dir); !out.OK {
		t.Fatalf("install: %v", out.Error)
	}
	if !Installed(c, dir) {
		t.Error("the pinned copy did not count as installed")
	}
	if entries, _ := os.ReadDir(dir); len(entries) != 1 {
		t.Errorf("left behind %v", entries)
	}
}

func sha256Hex(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}
