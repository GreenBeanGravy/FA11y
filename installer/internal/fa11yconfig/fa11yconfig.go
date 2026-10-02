// Package fa11yconfig reads the few FA11y settings the launcher needs from
// config\config.txt, without depending on Python.
package fa11yconfig

import (
	"bufio"
	"os"
	"strings"
)

// Bool returns the value of key from FA11y's INI-style config file, or
// fallback when the file or key is missing. Like FA11y, it searches every
// section and ignores the quoted description after the value:
//
//	AutoUpdates = true "Toggles automatic updates of FA11y."
func Bool(path, key string, fallback bool) bool {
	f, err := os.Open(path)
	if err != nil {
		return fallback
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || line[0] == '#' || line[0] == ';' || line[0] == '[' {
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if !ok || !strings.EqualFold(strings.TrimSpace(k), key) {
			continue
		}
		value, _, _ := strings.Cut(v, `"`)
		switch strings.ToLower(strings.TrimSpace(value)) {
		case "true", "yes", "on", "1":
			return true
		default:
			return false
		}
	}
	return fallback
}
