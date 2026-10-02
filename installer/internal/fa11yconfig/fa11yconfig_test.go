package fa11yconfig

import (
	"os"
	"path/filepath"
	"testing"
)

func TestBool(t *testing.T) {
	path := filepath.Join(t.TempDir(), "config.txt")
	content := "[Toggles]\nAutoUpdates = false \"Toggles automatic updates of FA11y.\"\nCreateDesktopShortcut = true\n"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		key      string
		fallback bool
		want     bool
	}{
		{"AutoUpdates", true, false},
		{"autoupdates", true, false},
		{"CreateDesktopShortcut", false, true},
		{"Missing", true, true},
	}
	for _, c := range cases {
		if got := Bool(path, c.key, c.fallback); got != c.want {
			t.Errorf("Bool(%q) = %v, want %v", c.key, got, c.want)
		}
	}
	if !Bool(filepath.Join(t.TempDir(), "absent.txt"), "AutoUpdates", true) {
		t.Error("missing file should return the fallback")
	}
}
