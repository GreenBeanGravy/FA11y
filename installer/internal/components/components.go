// Package components detects, downloads and installs the external pieces
// listed in the manifest (runtimes, drivers, tools).
package components

import (
	"fmt"
	"net/url"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"regexp"
	"strings"

	"golang.org/x/sys/windows/registry"

	"github.com/GreenBeanGravy/FA11y/installer/internal/console"
	"github.com/GreenBeanGravy/FA11y/installer/internal/fetch"
	"github.com/GreenBeanGravy/FA11y/installer/internal/manifest"
)

var envVar = regexp.MustCompile(`%([^%]+)%`)

// Expand replaces %VAR% with environment variables and %FA11Y_FILES% with
// the FA11y Files folder.
func Expand(s, filesDir string) string {
	return envVar.ReplaceAllStringFunc(s, func(m string) string {
		name := m[1 : len(m)-1]
		if strings.EqualFold(name, "FA11Y_FILES") {
			return filesDir
		}
		if v, ok := os.LookupEnv(name); ok {
			return v
		}
		return m
	})
}

// Installed reports whether every detect rule of c matches.
func Installed(c manifest.Component, filesDir string) bool {
	d := c.Detect
	if d.PathGlob != "" {
		matches, err := filepath.Glob(Expand(d.PathGlob, filesDir))
		if err != nil || len(matches) == 0 {
			return false
		}
	}
	if d.UninstallDisplayName != "" && !uninstallEntryExists(d.UninstallDisplayName) {
		return false
	}
	return true
}

func uninstallEntryExists(name string) bool {
	const key = `SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`
	roots := []struct {
		root   registry.Key
		access uint32
	}{
		{registry.LOCAL_MACHINE, registry.WOW64_64KEY},
		{registry.LOCAL_MACHINE, registry.WOW64_32KEY},
		{registry.CURRENT_USER, 0},
	}
	for _, r := range roots {
		k, err := registry.OpenKey(r.root, key, registry.ENUMERATE_SUB_KEYS|registry.READ|r.access)
		if err != nil {
			continue
		}
		subkeys, _ := k.ReadSubKeyNames(-1)
		for _, s := range subkeys {
			sk, err := registry.OpenKey(k, s, registry.QUERY_VALUE|r.access)
			if err != nil {
				continue
			}
			display, _, _ := sk.GetStringValue("DisplayName")
			sk.Close()
			if strings.Contains(strings.ToLower(display), strings.ToLower(name)) {
				k.Close()
				return true
			}
		}
		k.Close()
	}
	return false
}

// Expect returns the hash a component's download must have.
func Expect(c manifest.Component) fetch.Expect {
	return fetch.Expect{SHA256: c.Download.SHA256, SHA512: c.Download.SHA512}
}

// Download fetches c's installer into dir and returns its path.
func Download(c manifest.Component, dir string) (string, error) {
	u, err := url.Parse(c.Download.URL)
	if err != nil {
		return "", err
	}
	dest := filepath.Join(dir, c.ID+"-"+path.Base(u.Path))
	if fetch.VerifyFile(dest, Expect(c)) == nil {
		return dest, nil
	}
	err = fetch.FileProgress(c.Download.URL, dest, Expect(c), console.BytesProgress())
	console.Progress(-1)
	return dest, err
}

// Outcome is the result of installing one component.
type Outcome struct {
	OK     bool   `json:"ok"`
	Reboot bool   `json:"reboot,omitempty"`
	Code   int    `json:"code"`
	Error  string `json:"error,omitempty"`
}

// Install runs c's installer from file. Elevated components must be
// installed from an elevated process.
func Install(c manifest.Component, file, filesDir string) Outcome {
	if err := fetch.VerifyFile(file, Expect(c)); err != nil {
		return Outcome{Error: err.Error()}
	}
	var cmd *exec.Cmd
	switch c.Install.Type {
	case "file":
		dest := filepath.Join(filesDir, filepath.FromSlash(c.Install.Dest))
		if err := copyFile(file, dest); err != nil {
			return Outcome{Error: err.Error()}
		}
		return Outcome{OK: true}
	case "msi":
		cmd = exec.Command("msiexec.exe", append([]string{"/i", file}, c.Install.Args...)...)
	case "exe":
		cmd = exec.Command(file, c.Install.Args...)
	default:
		return Outcome{Error: fmt.Sprintf("unknown install type %q", c.Install.Type)}
	}
	console.Command(cmd)
	err := cmd.Run()
	code := 0
	if exitErr, ok := err.(*exec.ExitError); ok {
		code = exitErr.ExitCode()
	} else if err != nil {
		return Outcome{Error: err.Error()}
	}
	if !c.Install.SuccessCode(code) {
		return Outcome{Code: code, Error: fmt.Sprintf("installer exited with code %d", code)}
	}
	return Outcome{OK: true, Code: code, Reboot: manifest.RebootCodes[code]}
}

func copyFile(src, dest string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	tmp := dest + ".tmp"
	if err := os.WriteFile(tmp, data, 0o755); err != nil {
		return err
	}
	os.Remove(dest)
	return os.Rename(tmp, dest)
}
