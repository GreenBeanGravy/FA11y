package main

import (
	"archive/zip"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/GreenBeanGravy/FA11y/installer/internal/console"
	"github.com/GreenBeanGravy/FA11y/installer/internal/fetch"
	"github.com/GreenBeanGravy/FA11y/installer/internal/layout"
	"github.com/GreenBeanGravy/FA11y/installer/internal/manifest"
	"github.com/GreenBeanGravy/FA11y/installer/internal/pyenv"
)

func runtimeReady(l layout.Layout, py manifest.Python) bool {
	dir := l.RuntimeDir(py.Version)
	for _, f := range []string{"python.exe", filepath.Join("Lib", "os.py"), filepath.Join("Lib", "venv", "__init__.py")} {
		if _, err := os.Stat(filepath.Join(dir, f)); err != nil {
			return false
		}
	}
	return true
}

// ensureRuntime installs the private base Python from the official NuGet
// package. It reports whether anything was installed.
func ensureRuntime(l layout.Layout, py manifest.Python) (bool, error) {
	if runtimeReady(l, py) {
		return false, nil
	}
	console.Say("Downloading Python %s...", py.Version)
	pkg := filepath.Join(os.TempDir(), "fa11y-python-"+py.Version+".zip")
	defer os.Remove(pkg)
	err := fetch.FileProgress(py.URL, pkg, fetch.Expect{SHA256: py.SHA256}, console.BytesProgress())
	console.Progress(-1)
	if err != nil {
		return false, err
	}
	dir := l.RuntimeDir(py.Version)
	tmp := dir + ".partial"
	os.RemoveAll(tmp)
	if err := extract(pkg, py.ArchiveSubdir, tmp); err != nil {
		os.RemoveAll(tmp)
		return false, err
	}
	os.RemoveAll(dir)
	if err := os.Rename(tmp, dir); err != nil {
		return false, err
	}
	// Remove runtimes of other versions; the venv only uses this one.
	entries, _ := os.ReadDir(l.RuntimeRoot())
	for _, e := range entries {
		if e.IsDir() && e.Name() != filepath.Base(dir) && strings.HasPrefix(e.Name(), "python-") {
			os.RemoveAll(filepath.Join(l.RuntimeRoot(), e.Name()))
		}
	}
	return true, nil
}

// extract unpacks the entries under subdir/ of a zip into dest.
func extract(zipPath, subdir, dest string) error {
	r, err := zip.OpenReader(zipPath)
	if err != nil {
		return err
	}
	defer r.Close()
	prefix := strings.Trim(subdir, "/") + "/"
	for _, f := range r.File {
		name, err := url.PathUnescape(f.Name) // NuGet escapes some characters
		if err != nil {
			name = f.Name
		}
		name = strings.ReplaceAll(name, `\`, "/")
		rel, ok := strings.CutPrefix(name, prefix)
		if !ok || rel == "" || f.FileInfo().IsDir() {
			continue
		}
		target := filepath.Join(dest, filepath.FromSlash(rel))
		if !strings.HasPrefix(target, filepath.Clean(dest)+string(os.PathSeparator)) {
			return fmt.Errorf("unsafe path in archive: %s", f.Name)
		}
		if err := writeZipEntry(f, target); err != nil {
			return err
		}
	}
	return nil
}

func writeZipEntry(f *zip.File, target string) error {
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		return err
	}
	src, err := f.Open()
	if err != nil {
		return err
	}
	defer src.Close()
	out, err := os.Create(target)
	if err != nil {
		return err
	}
	_, err = io.Copy(out, src)
	if closeErr := out.Close(); err == nil {
		err = closeErr
	}
	return err
}

func venvReady(l layout.Layout, py manifest.Python) bool {
	if _, err := os.Stat(l.VenvPython()); err != nil {
		return false
	}
	cfg, err := pyenv.ReadConfig(l.VenvDir())
	return err == nil && cfg.Version() == py.Version
}

// ensureVenv creates the venv, or recreates it when its Python version
// differs from the manifest's. It reports whether the venv is new.
func ensureVenv(l layout.Layout, py manifest.Python) (bool, error) {
	if venvReady(l, py) {
		cfg, err := pyenv.ReadConfig(l.VenvDir())
		if err == nil {
			_, err = cfg.Relocate(l.RuntimeDir(py.Version))
		}
		return false, err
	}
	console.Say("Creating FA11y's Python environment...")
	if err := os.RemoveAll(l.VenvDir()); err != nil {
		return false, err
	}
	base := filepath.Join(l.RuntimeDir(py.Version), "python.exe")
	return true, runPython(l, base, "-E", "-s", "-m", "venv", l.VenvDir())
}

// ensureRequirements installs the requirements lock into the venv when it
// changed since the last install, or reinstalls every package when repair
// is set. It returns the lock's hash.
func ensureRequirements(l layout.Layout, lockName, installedHash string, repair bool) (string, bool, error) {
	lock := filepath.Join(l.Files, lockName)
	hash, changed, err := lockHash(l, lockName, installedHash)
	if err != nil || (!changed && !repair) {
		return hash, false, err
	}
	args := []string{"-E", "-m", "pip", "install",
		"--disable-pip-version-check", "--no-input", "--progress-bar", "off", "-q",
		"--require-hashes", "-r", lock}
	if repair && !changed {
		console.Say("Reinstalling Python packages to repair the install...")
		args = append(args, "--force-reinstall")
	} else {
		console.Say("Installing Python packages. The first install downloads about 200 MB and can take a few minutes...")
	}
	err = runPython(l, l.VenvPython(), args...)
	if err != nil {
		return "", false, fmt.Errorf("installing Python packages failed: %w", err)
	}
	return hash, true, nil
}

func runPython(l layout.Layout, python string, args ...string) error {
	cmd := exec.Command(python, args...)
	cmd.Dir = l.Files
	cmd.Env = pyenv.CleanEnv(os.Environ())
	console.Command(cmd)
	return cmd.Run()
}

func sha256Hex(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}
