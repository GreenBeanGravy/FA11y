package manifest

import (
	"fmt"
	"path/filepath"
	"testing"
)

func TestRepositoryManifestIsValid(t *testing.T) {
	m, err := Load(filepath.Join("..", "..", "manifest.json"))
	if err != nil {
		t.Fatal(err)
	}
	if !m.Sync.Excluded("installer/manifest.json") || !m.Sync.Excluded(".gitignore") {
		t.Error("installer files should be excluded")
	}
	if m.Sync.Excluded("lib/app/state.py") || m.Sync.Excluded("FA11y.py") {
		t.Error("FA11y files must be installed")
	}
	if !m.Sync.IsAddOnly("assets/sounds/update.ogg") || m.Sync.IsAddOnly("assets/images/x.png") {
		t.Error("only sounds are add-only")
	}
}

func TestParseRejectsBadComponents(t *testing.T) {
	base := `{"schema":1,"repo":"a/b","branch":"main","python":{"version":"3.12.9","url":"u","sha256":"h"},"components":[%s]}`
	bad := []string{
		`{"id":"x","detect":{},"download":{"url":"u","sha256":"h"},"install":{"type":"msi"}}`,
		`{"id":"x","detect":{"path_glob":"p"},"download":{"url":"u"},"install":{"type":"msi"}}`,
		`{"id":"x","detect":{"path_glob":"p"},"download":{"url":"u","sha256":"h"},"install":{"type":"zip"}}`,
		`{"id":"x","detect":{"path_glob":"p"},"download":{"url":"u","sha256":"h"},"install":{"type":"file"}}`,
	}
	for _, c := range bad {
		if _, err := Parse([]byte(fmt.Sprintf(base, c))); err == nil {
			t.Errorf("accepted %s", c)
		}
	}
	if _, err := Parse([]byte(`{"schema":2}`)); err == nil {
		t.Error("accepted unknown schema")
	}
}
