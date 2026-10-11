package filesync

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

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

func TestPendingSeesChangesWithoutAVersionBump(t *testing.T) {
	rules := manifest.Sync{Exclude: []string{"tests/"}, AddOnly: []string{"assets/sounds/"}}
	st := &state.State{Files: map[string]string{"FA11y.py": "a1", "lib/x.py": "b1", "lib/gone.py": "c1"}}
	tree := []Entry{
		{Path: "FA11y.py", SHA: "a1"},
		{Path: "lib/x.py", SHA: "b2"},           // changed
		{Path: "lib/new.py", SHA: "d1"},         // added
		{Path: "tests/t.py", SHA: "e1"},         // excluded: never installed
		{Path: "assets/sounds/s.ogg", SHA: "f"}, // add-only: users may change it
	}
	got := Pending(rules, tree, st)
	want := []string{"lib/gone.py", "lib/new.py", "lib/x.py"}
	if len(got) != len(want) {
		t.Fatalf("Pending = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("Pending = %v, want %v", got, want)
		}
	}
	st.Files = map[string]string{"FA11y.py": "a1", "lib/x.py": "b2", "lib/new.py": "d1"}
	if got := Pending(rules, tree, st); len(got) != 0 {
		t.Errorf("up to date install has pending %v", got)
	}
}

// A file the running FA11y still has loaded used to make Rename fail and abort
// the whole update. Now it is set aside and deleted by a later sync.
func TestSyncReplacesAFileInUseAndCleansItUpLater(t *testing.T) {
	src, dst := t.TempDir(), t.TempDir()
	ping, err := os.ReadFile(filepath.Join(os.Getenv("SystemRoot"), "System32", "PING.EXE"))
	if err != nil {
		t.Skip("ping.exe not available")
	}
	write(t, dst, "ui/bin/tool.exe", string(ping))
	running := exec.Command(filepath.Join(dst, "ui", "bin", "tool.exe"), "-n", "30", "127.0.0.1")
	if err := running.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { running.Process.Kill(); running.Wait() }()
	write(t, src, "ui/bin/tool.exe", "new build")

	st := &state.State{Files: map[string]string{}}
	tree, _ := Local{Dir: src}.Tree()
	if _, err := Sync(dst, Local{Dir: src}, manifest.Sync{}, tree, st, func(string, ...any) {}); err != nil {
		t.Fatalf("sync failed on a file in use: %v", err)
	}
	if b, _ := os.ReadFile(filepath.Join(dst, "ui", "bin", "tool.exe")); string(b) != "new build" {
		t.Error("file in use was not replaced")
	}
	if len(st.SetAside) != 1 || st.SetAside[0] != "ui/bin/tool.exe.old" {
		t.Fatalf("SetAside = %v", st.SetAside)
	}

	CleanupSetAside(dst, st) // still running: kept for next time
	if len(st.SetAside) != 1 {
		t.Fatal("dropped a file still in use from the cleanup list")
	}
	running.Process.Kill()
	running.Wait()
	time.Sleep(200 * time.Millisecond)
	CleanupSetAside(dst, st)
	if len(st.SetAside) != 0 {
		t.Errorf("SetAside = %v after the program closed", st.SetAside)
	}
	if _, err := os.Stat(filepath.Join(dst, "ui", "bin", "tool.exe.old")); err == nil {
		t.Error("set-aside copy left on disk")
	}
}
