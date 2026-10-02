package filesync

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/GreenBeanGravy/FA11y/installer/internal/manifest"
	"github.com/GreenBeanGravy/FA11y/installer/internal/state"
)

func TestBlobSHAMatchesGit(t *testing.T) {
	p := filepath.Join(t.TempDir(), "f")
	os.WriteFile(p, []byte("hello\n"), 0o644)
	// git hash-object of "hello\n"
	if got := BlobSHA(p); got != "ce013625030ba8dba906f756967f9e9ca394464a" {
		t.Errorf("BlobSHA = %s", got)
	}
}

func write(t *testing.T, root, rel, content string) {
	t.Helper()
	p := filepath.Join(root, filepath.FromSlash(rel))
	os.MkdirAll(filepath.Dir(p), 0o755)
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestSyncFromLocal(t *testing.T) {
	src, dst := t.TempDir(), t.TempDir()
	write(t, src, "FA11y.py", "v1")
	write(t, src, "lib/a.py", "a")
	write(t, src, "tests/test_a.py", "t")
	write(t, src, "assets/sounds/s.ogg", "upstream")
	write(t, dst, "assets/sounds/s.ogg", "custom")
	write(t, dst, "config/config.txt", "user")

	rules := manifest.Sync{Exclude: []string{"tests/"}, AddOnly: []string{"assets/sounds/"}}
	st := &state.State{Files: map[string]string{}}
	sync := func() Result {
		tree, err := Local{Dir: src}.Tree()
		if err != nil {
			t.Fatal(err)
		}
		res, err := Sync(dst, Local{Dir: src}, rules, tree, st, func(string, ...any) {})
		if err != nil {
			t.Fatal(err)
		}
		return res
	}

	if res := sync(); len(res.Updated) != 2 {
		t.Fatalf("first sync updated %v", res.Updated)
	}
	if _, err := os.Stat(filepath.Join(dst, "tests")); err == nil {
		t.Error("excluded folder was installed")
	}
	if b, _ := os.ReadFile(filepath.Join(dst, "assets/sounds/s.ogg")); string(b) != "custom" {
		t.Error("add-only file was overwritten")
	}
	if res := sync(); res.Changed() {
		t.Errorf("second sync changed %v", res)
	}

	os.Remove(filepath.Join(src, "lib/a.py"))
	res := sync()
	if len(res.Removed) != 1 {
		t.Fatalf("removed %v", res.Removed)
	}
	if _, err := os.Stat(filepath.Join(dst, "lib")); err == nil {
		t.Error("empty folder left behind")
	}
	if b, _ := os.ReadFile(filepath.Join(dst, "config/config.txt")); string(b) != "user" {
		t.Error("user file touched")
	}
}
