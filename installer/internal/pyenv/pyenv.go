// Package pyenv keeps FA11y's Python isolated from anything else installed
// on the user's machine.
package pyenv

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// CleanEnv returns base without any PYTHON* or VIRTUAL_ENV variables, so a
// global PYTHONPATH or PYTHONHOME cannot leak other Python installs into
// FA11y, plus the variables FA11y always runs with.
func CleanEnv(base []string) []string {
	env := make([]string, 0, len(base)+2)
	for _, kv := range base {
		name, _, _ := strings.Cut(kv, "=")
		upper := strings.ToUpper(name)
		if strings.HasPrefix(upper, "PYTHON") || upper == "VIRTUAL_ENV" {
			continue
		}
		env = append(env, kv)
	}
	return append(env,
		"PYTHONNOUSERSITE=1",
		"PYGAME_HIDE_SUPPORT_PROMPT=hide",
	)
}

// Config is the parsed content of a venv's pyvenv.cfg.
type Config struct {
	path  string
	lines []string
}

// ReadConfig parses venvDir\pyvenv.cfg.
func ReadConfig(venvDir string) (*Config, error) {
	path := filepath.Join(venvDir, "pyvenv.cfg")
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	cfg := &Config{path: path}
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		cfg.lines = append(cfg.lines, scanner.Text())
	}
	return cfg, scanner.Err()
}

// Get returns the value of key, or "" when absent.
func (c *Config) Get(key string) string {
	for _, line := range c.lines {
		k, v, ok := strings.Cut(line, "=")
		if ok && strings.EqualFold(strings.TrimSpace(k), key) {
			return strings.TrimSpace(v)
		}
	}
	return ""
}

func (c *Config) set(key, value string) {
	for i, line := range c.lines {
		k, _, ok := strings.Cut(line, "=")
		if ok && strings.EqualFold(strings.TrimSpace(k), key) {
			c.lines[i] = key + " = " + value
			return
		}
	}
	c.lines = append(c.lines, key+" = "+value)
}

// Version returns the venv's Python version, e.g. "3.12.9".
func (c *Config) Version() string {
	if v := c.Get("version_info"); v != "" {
		return v
	}
	return c.Get("version")
}

// Relocate points the venv at runtimeDir when it points anywhere else, which
// happens after the user moves the install folder. It reports whether the
// file changed.
func (c *Config) Relocate(runtimeDir string) (bool, error) {
	if strings.EqualFold(filepath.Clean(c.Get("home")), filepath.Clean(runtimeDir)) {
		return false, nil
	}
	if _, err := os.Stat(filepath.Join(runtimeDir, "python.exe")); err != nil {
		return false, fmt.Errorf("base Python not found in %s: %w", runtimeDir, err)
	}
	c.set("home", runtimeDir)
	if c.Get("executable") != "" {
		c.set("executable", filepath.Join(runtimeDir, "python.exe"))
	}
	data := strings.Join(c.lines, "\n") + "\n"
	return true, os.WriteFile(c.path, []byte(data), 0o644)
}
