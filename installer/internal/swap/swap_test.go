package swap

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func write(t *testing.T, p, content string) {
	t.Helper()
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func read(t *testing.T, p string) string {
	t.Helper()
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

// running copies ping.exe to dir as name and runs it, so the file is a
// loaded image the way a running Updater.exe or launcher is: Windows won't
// delete it but will rename it.
func running(t *testing.T, dir, name string) string {
	t.Helper()
	exe := filepath.Join(dir, name)
	data, err := os.ReadFile(filepath.Join(os.Getenv("SystemRoot"), "System32", "PING.EXE"))
	if err != nil {
		t.Skip("ping.exe not available:", err)
	}
	if err := os.WriteFile(exe, data, 0o755); err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(exe, "-n", "30", "127.0.0.1")
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		cmd.Process.Kill()
		cmd.Wait()
		time.Sleep(100 * time.Millisecond)
	})
	if err := os.Remove(exe); err == nil {
		t.Skip("this system deletes running executables; nothing to test")
	}
	return exe
}

func TestIntoReplacesAnUnusedFileWithoutLeavingAnything(t *testing.T) {
	dir := t.TempDir()
	target, staged := filepath.Join(dir, "a.exe"), filepath.Join(dir, "a.exe.new")
	write(t, target, "old")
	write(t, staged, "new")
	aside, err := Into(staged, target)
	if err != nil || aside != "" {
		t.Fatalf("Into = %q, %v", aside, err)
	}
	if read(t, target) != "new" {
		t.Error("target not replaced")
	}
	if entries, _ := os.ReadDir(dir); len(entries) != 1 {
		t.Errorf("left behind %v", entries)
	}
}

func TestIntoSetsARunningFileAsideAndALaterOneGetsANewName(t *testing.T) {
	dir := t.TempDir()
	target := running(t, dir, "Updater.exe")

	staged := filepath.Join(dir, "Updater.exe.new")
	write(t, staged, "v2")
	aside, err := Into(staged, target)
	if err != nil {
		t.Fatal(err)
	}
	if aside != target+".old" || read(t, target) != "v2" {
		t.Fatalf("aside %q, target %q", aside, read(t, target))
	}

	// The program set aside is still running, so ".old" is taken: before the
	// fix this made every later update fail.
	second := running(t, dir, "Second.exe")
	if err := os.Rename(second, target+".tmp"); err != nil {
		t.Fatal(err)
	}
	os.Remove(target)
	if err := os.Rename(target+".tmp", target); err != nil {
		t.Fatal(err)
	}
	write(t, staged, "v3")
	aside, err = Into(staged, target)
	if err != nil {
		t.Fatal(err)
	}
	if aside != target+".1.old" || read(t, target) != "v3" {
		t.Fatalf("aside %q", aside)
	}

	if left := Cleanup(target); len(left) != 2 {
		t.Errorf("cleanup removed a file in use, or kept one: %v", left)
	}
}

func TestCleanupRemovesEveryUnusedCopyAndOnlyThose(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "FA11y_Launcher.exe")
	for _, name := range []string{"FA11y_Launcher.exe", "FA11y_Launcher.exe.old", "FA11y_Launcher.exe.1.old",
		"FA11y_Launcher.exe.12.old", "FA11y_Launcher.exe.new", "FA11y_Launcher.exe.x.old", "Other.exe.old"} {
		write(t, filepath.Join(dir, name), name)
	}
	if left := Cleanup(target); len(left) != 0 {
		t.Fatalf("left %v", left)
	}
	var names []string
	entries, _ := os.ReadDir(dir)
	for _, e := range entries {
		names = append(names, e.Name())
	}
	want := []string{"FA11y_Launcher.exe", "FA11y_Launcher.exe.x.old", "Other.exe.old"}
	if len(names) != len(want) {
		t.Fatalf("left %v, want %v", names, want)
	}
	for i := range want {
		if names[i] != want[i] {
			t.Fatalf("left %v, want %v", names, want)
		}
	}
}

func TestCleanupHandlesGlobCharactersInThePath(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "FA11y [beta]")
	os.MkdirAll(dir, 0o755)
	target := filepath.Join(dir, "Updater.exe")
	write(t, target+".old", "x")
	Cleanup(target)
	if _, err := os.Stat(target + ".old"); err == nil {
		t.Error("not removed from a folder with brackets in its name")
	}
}
