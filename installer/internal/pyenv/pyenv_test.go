package pyenv

import (
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

func TestCleanEnv(t *testing.T) {
	env := CleanEnv([]string{
		`PATH=C:\Windows`, `PYTHONPATH=C:\OpenVINO\python`, `PythonHome=C:\x`,
		`VIRTUAL_ENV=C:\other`, `USERPROFILE=C:\Users\me`,
	})
	for _, kv := range env {
		upper := strings.ToUpper(kv)
		for _, banned := range []string{"PYTHONPATH=", "PYTHONHOME=", "VIRTUAL_ENV="} {
			if strings.HasPrefix(upper, banned) {
				t.Errorf("leaked %q", kv)
			}
		}
	}
	for _, want := range []string{`PATH=C:\Windows`, `USERPROFILE=C:\Users\me`, "PYTHONNOUSERSITE=1"} {
		if !slices.Contains(env, want) {
			t.Errorf("missing %q", want)
		}
	}
}

func TestRelocate(t *testing.T) {
	dir := t.TempDir()
	venv := filepath.Join(dir, ".venv")
	runtime := filepath.Join(dir, "runtime", "python-3.12.9")
	for _, d := range []string{venv, runtime} {
		if err := os.MkdirAll(d, 0o755); err != nil {
			t.Fatal(err)
		}
	}
	os.WriteFile(filepath.Join(runtime, "python.exe"), nil, 0o644)
	old := "home = D:\\Old\\runtime\\python-3.12.9\n" +
		"include-system-site-packages = false\n" +
		"version = 3.12.9\n" +
		"executable = D:\\Old\\runtime\\python-3.12.9\\python.exe\n"
	os.WriteFile(filepath.Join(venv, "pyvenv.cfg"), []byte(old), 0o644)

	cfg, err := ReadConfig(venv)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Version() != "3.12.9" {
		t.Fatalf("Version() = %q", cfg.Version())
	}
	changed, err := cfg.Relocate(runtime)
	if err != nil || !changed {
		t.Fatalf("Relocate() = %v, %v; want true, nil", changed, err)
	}
	cfg, _ = ReadConfig(venv)
	if cfg.Get("home") != runtime || cfg.Get("executable") != filepath.Join(runtime, "python.exe") {
		t.Errorf("not relocated: home=%q executable=%q", cfg.Get("home"), cfg.Get("executable"))
	}
	if cfg.Get("include-system-site-packages") != "false" {
		t.Error("unrelated keys must be kept")
	}
	if changed, _ := cfg.Relocate(runtime); changed {
		t.Error("second Relocate should be a no-op")
	}
}
