// Package fetch downloads files over HTTPS with retries and hash checks.
package fetch

import (
	"crypto/sha256"
	"crypto/sha512"
	"encoding/hex"
	"fmt"
	"hash"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Persistent makes every request retry until it succeeds (Monarch mode),
// for users on unreliable connections.
var Persistent = false

const attempts = 3

var client = &http.Client{Timeout: 10 * time.Minute}

// Bytes downloads url into memory.
func Bytes(url string) ([]byte, error) {
	var data []byte
	err := retry(url, func() error {
		body, err := get(url)
		if err != nil {
			return err
		}
		defer body.Close()
		data, err = io.ReadAll(body)
		return err
	})
	return data, err
}

// Expect is the hash a download must have. Leave both empty to skip the check.
type Expect struct {
	SHA256 string
	SHA512 string
}

// File downloads url to dest, verifying the hash before dest appears. It
// writes to a temporary file first, so dest is never left half-written.
func File(url, dest string, want Expect) error {
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	return retry(url, func() error {
		body, err := get(url)
		if err != nil {
			return err
		}
		defer body.Close()
		tmp, err := os.CreateTemp(filepath.Dir(dest), ".download-*")
		if err != nil {
			return err
		}
		defer os.Remove(tmp.Name())

		var h hash.Hash
		var expected string
		switch {
		case want.SHA512 != "":
			h, expected = sha512.New(), want.SHA512
		case want.SHA256 != "":
			h, expected = sha256.New(), want.SHA256
		}
		var w io.Writer = tmp
		if h != nil {
			w = io.MultiWriter(tmp, h)
		}
		_, err = io.Copy(w, body)
		if closeErr := tmp.Close(); err == nil {
			err = closeErr
		}
		if err != nil {
			return err
		}
		if h != nil {
			if got := hex.EncodeToString(h.Sum(nil)); !strings.EqualFold(got, expected) {
				return &HashError{URL: url, Got: got, Want: expected}
			}
		}
		os.Remove(dest)
		return os.Rename(tmp.Name(), dest)
	})
}

// HashError means a download did not match its expected hash. It is not
// retried: the server is serving different bytes than the manifest pins.
type HashError struct{ URL, Got, Want string }

func (e *HashError) Error() string {
	return fmt.Sprintf("%s has the wrong hash (got %s, want %s)", e.URL, e.Got, e.Want)
}

// VerifyFile checks a file already on disk against want.
func VerifyFile(path string, want Expect) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	var h hash.Hash
	expected := want.SHA256
	if want.SHA512 != "" {
		h, expected = sha512.New(), want.SHA512
	} else {
		h = sha256.New()
	}
	if _, err := io.Copy(h, f); err != nil {
		return err
	}
	if got := hex.EncodeToString(h.Sum(nil)); !strings.EqualFold(got, expected) {
		return &HashError{URL: path, Got: got, Want: expected}
	}
	return nil
}

func get(url string) (io.ReadCloser, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "FA11y-Updater")
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		resp.Body.Close()
		return nil, &StatusError{URL: url, Code: resp.StatusCode}
	}
	return resp.Body, nil
}

// StatusError is a non-200 HTTP response.
type StatusError struct {
	URL  string
	Code int
}

func (e *StatusError) Error() string { return fmt.Sprintf("%s returned HTTP %d", e.URL, e.Code) }

func retry(url string, do func() error) error {
	var err error
	for i := 0; Persistent || i < attempts; i++ {
		if err = do(); err == nil {
			return nil
		}
		if _, ok := err.(*HashError); ok {
			return err
		}
		if se, ok := err.(*StatusError); ok && se.Code == http.StatusNotFound {
			return err
		}
		time.Sleep(time.Duration(min(i+1, 5)) * 2 * time.Second)
	}
	return err
}
