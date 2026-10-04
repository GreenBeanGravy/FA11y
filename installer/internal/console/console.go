// Package console holds the status output the launcher and updater share.
// Output is plain text so screen readers read it as it appears in the
// console window. The updater can switch to a progress window instead
// (UseWindow); Say, Fail and Progress then go to that window, and callers do
// not change.
package console

import (
	"bufio"
	"bytes"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"

	"github.com/GreenBeanGravy/FA11y/installer/internal/progresswin"
)

var (
	kernel32           = syscall.NewLazyDLL("kernel32.dll")
	setConsoleTitle    = kernel32.NewProc("SetConsoleTitleW")
	getConsoleWindow   = kernel32.NewProc("GetConsoleWindow")
	getConsoleMode     = kernel32.NewProc("GetConsoleMode")
	getConsoleProcList = kernel32.NewProc("GetConsoleProcessList")
	allocConsole       = kernel32.NewProc("AllocConsole")
	freeConsole        = kernel32.NewProc("FreeConsole")
	title              = ""
)

const createNoWindow = 0x08000000

var (
	mu         sync.Mutex
	wantWindow bool
	win        *progresswin.Window
	lastStatus string
)

// SetTitle sets the console window title, now or when Ensure opens one.
func SetTitle(text string) {
	title = text
	p, err := syscall.UTF16PtrFromString(text)
	if err == nil {
		setConsoleTitle.Call(uintptr(unsafe.Pointer(p)))
	}
}

// OwnsConsole reports whether the console this program writes to was made
// for it, as when Updater.exe is double clicked, rather than being a
// terminal the user started it from or a pipe or file.
func OwnsConsole() bool {
	var mode uint32
	if ok, _, _ := getConsoleMode.Call(os.Stdout.Fd(), uintptr(unsafe.Pointer(&mode))); ok == 0 {
		return false
	}
	var pids [2]uint32
	n, _, _ := getConsoleProcList.Call(uintptr(unsafe.Pointer(&pids[0])), uintptr(len(pids)))
	return n == 1
}

// UseWindow sends status output to a progress window instead of the
// console. The window opens with the first line, so a program that has
// nothing to say shows nothing. The console the program started with, if
// any, is released.
func UseWindow() {
	mu.Lock()
	defer mu.Unlock()
	wantWindow = true
	freeConsole.Call()
}

// InWindow reports whether output goes to the progress window.
func InWindow() bool {
	mu.Lock()
	defer mu.Unlock()
	return wantWindow
}

// window returns the progress window, opening it the first time. It returns
// nil in console mode, or when the window cannot be made, in which case
// output falls back to a console.
func window() *progresswin.Window {
	mu.Lock()
	defer mu.Unlock()
	if !wantWindow {
		return nil
	}
	if win == nil {
		w, err := progresswin.Open(title)
		if err != nil {
			wantWindow = false
			return nil
		}
		win = w
	}
	return win
}

// Ensure gives a windowless program (FA11y_Launcher.exe is built with
// -H windowsgui) a console window the first time it has something to
// show. Say and Fail call it, so the launcher only opens a window when it
// installs, updates or reports an error. A program that already has a
// console, even a hidden one, keeps it.
func Ensure() {
	if window, _, _ := getConsoleWindow.Call(); window != 0 {
		return
	}
	if ok, _, _ := allocConsole.Call(); ok == 0 {
		return
	}
	if out, err := os.OpenFile("CONOUT$", os.O_RDWR, 0); err == nil {
		os.Stdout, os.Stderr = out, out
	}
	if in, err := os.OpenFile("CONIN$", os.O_RDWR, 0); err == nil {
		os.Stdin = in
	}
	if title != "" {
		SetTitle(title)
	}
}

// Say prints one line of status.
func Say(format string, args ...any) {
	if w := window(); w != nil {
		text := fmt.Sprintf(format, args...)
		mu.Lock()
		lastStatus = text
		mu.Unlock()
		w.SetStatus(text, progresswin.Info)
		w.Log(text)
		return
	}
	Ensure()
	fmt.Printf(format+"\n", args...)
}

// Progress shows how far the current step is, from 0 to 100, or -1 when
// that isn't known. Only the progress window shows it.
func Progress(percent float64) {
	if w := window(); w != nil {
		w.SetProgress(percent)
	}
}

// BytesProgress returns a download callback for fetch.FileProgress that
// reports the percent downloaded, and goes back to unknown when the size
// isn't. A step to the next whole percent is the only thing it passes on.
func BytesProgress() func(done, total int64) {
	last := -2
	return func(done, total int64) {
		percent := -1
		if total > 0 {
			percent = int(done * 100 / total)
		}
		if percent != last {
			last = percent
			Progress(float64(percent))
		}
	}
}

// Fail prints an error, waits for Enter (or for the window to be closed) so
// the message can be read, and exits with code.
func Fail(code int, format string, args ...any) {
	if w := window(); w != nil {
		text := fmt.Sprintf("Error: "+format, args...)
		w.SetStatus(text, progresswin.Failure)
		w.Log(text)
		w.Finish(0)
		os.Exit(code)
	}
	Ensure()
	fmt.Printf("Error: "+format+"\n", args...)
	fmt.Println("Press Enter to close.")
	bufio.NewReader(os.Stdin).ReadString('\n')
	os.Exit(code)
}

// Finish ends a successful run. In a console it says it is closing and
// waits d. In the window it enables Close and closes after d.
func Finish(d time.Duration) {
	text := fmt.Sprintf("Closing in %d seconds.", int(d.Seconds()))
	if w := window(); w != nil {
		mu.Lock()
		status := lastStatus
		mu.Unlock()
		w.SetStatus(status, progresswin.Success)
		w.Log(text)
		w.Finish(d)
		return
	}
	Say("%s", text)
	time.Sleep(d)
}

// Ask asks a yes or no question in the window. It reports false in a
// console, where callers ask for themselves.
func Ask(question string) bool {
	if w := window(); w != nil {
		return w.Ask(question)
	}
	return false
}

// Hide takes the window off the screen before another process shows its own.
func Hide() {
	mu.Lock()
	w := win
	mu.Unlock()
	if w != nil {
		w.Hide()
	}
}

// Command points cmd's output at the console, or at the window's log, and
// keeps it from opening a console window of its own.
func Command(cmd *exec.Cmd) {
	if !InWindow() {
		cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
		return
	}
	lw := &lineWriter{}
	cmd.Stdout, cmd.Stderr = lw, lw
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
}

// HideChildConsole is what the launcher sets on the updater: it starts the
// updater without a console window, so only the progress window shows.
func HideChildConsole(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
}

// lineWriter appends a child's output to the window's log, line by line.
type lineWriter struct {
	mu  sync.Mutex
	buf []byte
}

var _ io.Writer = (*lineWriter)(nil)

func (l *lineWriter) Write(p []byte) (int, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.buf = append(l.buf, p...)
	for {
		i := bytes.IndexByte(l.buf, '\n')
		if i < 0 {
			return len(p), nil
		}
		line := strings.TrimRight(string(l.buf[:i]), "\r")
		l.buf = l.buf[i+1:]
		if w := window(); w != nil && strings.TrimSpace(line) != "" {
			w.Log(line)
		}
	}
}
