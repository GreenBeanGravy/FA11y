// Package progresswin is the small native window Updater.exe shows while it
// installs or updates FA11y. It is plain Win32 (no .NET, which may not be
// installed yet) and follows FA11y's dark theme.
//
// The window is built for screen readers first: a read-only log holds every
// status line and has the focus, so the lines can be reviewed with the arrow
// keys and a new line is read as it is appended. The status line above the
// log raises a name-change event for each new line, and the Close button is
// enabled once the work is over.
//
// The window runs its own message loop on a locked OS thread. Every method
// is safe to call from any goroutine.
package progresswin

import (
	"os"
	"runtime"
	"sync"
	"syscall"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

// Kind colors the status line.
type Kind int

const (
	Info Kind = iota
	Success
	Failure
)

// FA11y's colors as COLORREF (0x00BBGGRR). They match
// ui/src/FA11y.UI/Theme/Colors.xaml.
const (
	colorWindow  = 0x1E1E1E
	colorCard    = 0x252525
	colorTrack   = 0x2E3030 // PressedBg
	colorText    = 0xDFE6E8
	colorSecond  = 0xA9B2B4 // TextSecondary
	colorMuted   = 0x808788 // TextMuted
	colorAccent  = 0xDD8A37
	colorSuccess = 0x59C497
	colorDanger  = 0x9595F0
)

const (
	wmDestroy       = 0x0002
	wmActivate      = 0x0006
	wmClose         = 0x0010
	wmCommand       = 0x0111
	wmTimer         = 0x0113
	wmCtlColorDlg   = 0x0136
	wmCtlColorEdit  = 0x0133
	wmCtlColorStat  = 0x0138
	wmSetFont       = 0x0030
	wmApp           = 0x8000
	wsOverlapped    = 0x00000000
	wsCaption       = 0x00C00000
	wsSysMenu       = 0x00080000
	wsMinimizeBox   = 0x00020000
	wsChild         = 0x40000000
	wsVisible       = 0x10000000
	wsDisabled      = 0x08000000
	wsTabStop       = 0x00010000
	wsBorder        = 0x00800000
	wsVScroll       = 0x00200000
	esMultiline     = 0x0004
	esAutoVScroll   = 0x0040
	esReadOnly      = 0x0800
	esNoHideSel     = 0x0100
	ssNoPrefix      = 0x0080
	bsPushButton    = 0x0000
	pbsSmooth       = 0x01
	pbsMarquee      = 0x08
	pbmSetPos       = 0x0402
	pbmSetMarquee   = 0x040A
	pbmSetBarColor  = 0x0409
	pbmSetBkColor   = 0x2001
	emSetSel        = 0x00B1
	emScrollCaret   = 0x00B7
	emReplaceSel    = 0x00C2
	emLimitText     = 0x00C5
	idcCancel       = 2
	idClose         = 100
	timerClose      = 1
	swHide          = 0
	swShow          = 5

	csHRedraw       = 0x0002
	csVRedraw       = 0x0001
	colorWindowIdx  = 5
	idcArrow        = 32512
	mbYesNo         = 0x4
	mbIconQuestion  = 0x20
	idYes           = 6
	dwmaDarkMode    = 20

	eventNameChange = 0x800C
	eventValChange  = 0x800E
	eventLiveRegion = 0x8019
	iccProgress     = 0x20
	sbPixelsPerInch = 90 // LOGPIXELSX
)

var (
	user32   = windows.NewLazySystemDLL("user32.dll")
	gdi32    = windows.NewLazySystemDLL("gdi32.dll")
	kernel32 = windows.NewLazySystemDLL("kernel32.dll")
	comctl32 = windows.NewLazySystemDLL("comctl32.dll")
	uxtheme  = windows.NewLazySystemDLL("uxtheme.dll")
	dwmapi   = windows.NewLazySystemDLL("dwmapi.dll")

	registerClassEx   = user32.NewProc("RegisterClassExW")
	createWindowEx    = user32.NewProc("CreateWindowExW")
	defWindowProc     = user32.NewProc("DefWindowProcW")
	showWindow        = user32.NewProc("ShowWindow")
	getMessage        = user32.NewProc("GetMessageW")
	translateMessage  = user32.NewProc("TranslateMessage")
	dispatchMessage   = user32.NewProc("DispatchMessageW")
	isDialogMessage   = user32.NewProc("IsDialogMessageW")
	postMessage       = user32.NewProc("PostMessageW")
	sendMessage       = user32.NewProc("SendMessageW")
	setWindowText     = user32.NewProc("SetWindowTextW")
	getWindowTextLen  = user32.NewProc("GetWindowTextLengthW")
	setFocus          = user32.NewProc("SetFocus")
	getFocus          = user32.NewProc("GetFocus")
	enableWindow      = user32.NewProc("EnableWindow")
	destroyWindow     = user32.NewProc("DestroyWindow")
	postQuitMessage   = user32.NewProc("PostQuitMessage")
	setTimer          = user32.NewProc("SetTimer")
	killTimer         = user32.NewProc("KillTimer")
	loadCursor        = user32.NewProc("LoadCursorW")
	loadIcon          = user32.NewProc("LoadIconW")
	getSystemMetrics  = user32.NewProc("GetSystemMetrics")
	adjustWindowRect  = user32.NewProc("AdjustWindowRectEx")
	setForeground     = user32.NewProc("SetForegroundWindow")
	notifyWinEvent    = user32.NewProc("NotifyWinEvent")
	getWindowLongPtr  = user32.NewProc("GetWindowLongPtrW")
	setWindowLongPtr  = user32.NewProc("SetWindowLongPtrW")
	messageBox        = user32.NewProc("MessageBoxW")
	setDpiAwareness   = user32.NewProc("SetProcessDpiAwarenessContext")
	setProcessDPIAwre = user32.NewProc("SetProcessDPIAware")
	getDpiForSystem   = user32.NewProc("GetDpiForSystem")
	getDC             = user32.NewProc("GetDC")
	releaseDC         = user32.NewProc("ReleaseDC")
	getDeviceCaps     = gdi32.NewProc("GetDeviceCaps")
	createSolidBrush  = gdi32.NewProc("CreateSolidBrush")
	createFont        = gdi32.NewProc("CreateFontW")
	setTextColor      = gdi32.NewProc("SetTextColor")
	setBkColor        = gdi32.NewProc("SetBkColor")
	getModuleHandle   = kernel32.NewProc("GetModuleHandleW")
	createActCtx      = kernel32.NewProc("CreateActCtxW")
	activateActCtx    = kernel32.NewProc("ActivateActCtx")
	initCommonCtrls   = comctl32.NewProc("InitCommonControlsEx")
	setWindowTheme    = uxtheme.NewProc("SetWindowTheme")
	dwmSetWindowAttr  = dwmapi.NewProc("DwmSetWindowAttribute")
)

type wndClassEx struct {
	size       uint32
	style      uint32
	wndProc    uintptr
	clsExtra   int32
	wndExtra   int32
	instance   uintptr
	icon       uintptr
	cursor     uintptr
	background uintptr
	menuName   *uint16
	className  *uint16
	iconSmall  uintptr
}

type msg struct {
	hwnd    uintptr
	message uint32
	wParam  uintptr
	lParam  uintptr
	time    uint32
	pt      [2]int32
	private uint32
}

type rect struct{ left, top, right, bottom int32 }

type actCtx struct {
	size     uint32
	flags    uint32
	source   *uint16
	arch     uint16
	langID   uint16
	assembly *uint16
	resource *uint16
	app      *uint16
	module   uintptr
}

type initCommonControls struct{ size, icc uint32 }

// The window procedure is a C callback and has no receiver, so the one
// window lives here.
var current *Window

// -16 and -4 as unsigned arguments.
const (
	gwlStyle    = ^uintptr(15)
	objidClient = ^uintptr(3)
)

// Window is the progress window.
type Window struct {
	hwnd, title, bar, status, logLabel, log, button uintptr
	fontText, fontTitle                              uintptr
	brushWindow, brushCard                           uintptr
	dpi                                              int

	// Touched only on the window's thread.
	finished  bool
	kind      Kind
	marquee   bool
	lastFocus uintptr
	hasLog    bool

	mu     sync.Mutex
	queue  []func()
	ready  chan error
	closed chan struct{}
}

// Open creates and shows the window on its own thread.
func Open(title string) (*Window, error) {
	w := &Window{ready: make(chan error, 1), closed: make(chan struct{})}
	go w.run(title)
	if err := <-w.ready; err != nil {
		return nil, err
	}
	return w, nil
}

func (w *Window) run(title string) {
	runtime.LockOSThread()
	defer close(w.closed)
	if err := w.create(title); err != nil {
		w.ready <- err
		return
	}
	w.ready <- nil
	var m msg
	for {
		r, _, _ := getMessage.Call(uintptr(unsafe.Pointer(&m)), 0, 0, 0)
		if int32(r) <= 0 {
			return
		}
		if ok, _, _ := isDialogMessage.Call(w.hwnd, uintptr(unsafe.Pointer(&m))); ok != 0 {
			continue
		}
		translateMessage.Call(uintptr(unsafe.Pointer(&m)))
		dispatchMessage.Call(uintptr(unsafe.Pointer(&m)))
	}
}

// useCommonControls6 makes this thread load comctl32 version 6, which has
// the marquee progress bar and the themes. Updater.exe has no manifest, so
// it activates one from a temporary file.
func useCommonControls6() {
	const manifest = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0"><dependency><dependentAssembly>` +
		`<assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"/>` +
		`</dependentAssembly></dependency></assembly>`
	f, err := os.CreateTemp("", "fa11y-*.manifest")
	if err != nil {
		return
	}
	defer os.Remove(f.Name())
	_, err = f.WriteString(manifest)
	if closeErr := f.Close(); err != nil || closeErr != nil {
		return
	}
	src, _ := windows.UTF16PtrFromString(f.Name())
	ctx := actCtx{source: src}
	ctx.size = uint32(unsafe.Sizeof(ctx))
	h, _, _ := createActCtx.Call(uintptr(unsafe.Pointer(&ctx)))
	if h == ^uintptr(0) {
		return
	}
	var cookie uintptr
	activateActCtx.Call(h, uintptr(unsafe.Pointer(&cookie)))
}

func utf16(s string) uintptr {
	p, _ := windows.UTF16PtrFromString(s)
	return uintptr(unsafe.Pointer(p))
}

func (w *Window) scale(n int) uintptr { return uintptr(n * w.dpi / 96) }

func (w *Window) child(class string, text string, style, exStyle uint32, x, y, cx, cy int, id uintptr) uintptr {
	h, _, _ := createWindowEx.Call(uintptr(exStyle), utf16(class), utf16(text), uintptr(style|wsChild|wsVisible),
		w.scale(x), w.scale(y), w.scale(cx), w.scale(cy), w.hwnd, id, 0, 0)
	return h
}

func (w *Window) create(title string) error {
	// System DPI awareness: crisp text without handling WM_DPICHANGED.
	if ok, _, _ := setDpiAwareness.Call(^uintptr(1)); ok == 0 {
		setProcessDPIAwre.Call()
	}
	useCommonControls6()
	icc := initCommonControls{icc: iccProgress}
	icc.size = uint32(unsafe.Sizeof(icc))
	initCommonCtrls.Call(uintptr(unsafe.Pointer(&icc)))

	w.dpi = 96
	if d, _, _ := getDpiForSystem.Call(); d != 0 {
		w.dpi = int(d)
	} else if dc, _, _ := getDC.Call(0); dc != 0 {
		d, _, _ := getDeviceCaps.Call(dc, sbPixelsPerInch)
		releaseDC.Call(0, dc)
		w.dpi = int(d)
	}

	w.brushWindow, _, _ = createSolidBrush.Call(colorWindow)
	w.brushCard, _, _ = createSolidBrush.Call(colorCard)
	font := func(points, weight int) uintptr {
		h, _, _ := createFont.Call(uintptr(-points*w.dpi/72), 0, 0, 0, uintptr(weight), 0, 0, 0, 1, 0, 0, 5, 0, utf16("Segoe UI"))
		return h
	}
	w.fontText, w.fontTitle = font(10, 400), font(16, 600)

	instance, _, _ := getModuleHandle.Call(0)
	icon, _, _ := loadIcon.Call(instance, 1) // the icon in Updater.exe's resources
	cursor, _, _ := loadCursor.Call(0, idcArrow)
	class := wndClassEx{
		style:      csHRedraw | csVRedraw,
		wndProc:    syscall.NewCallback(wndProc),
		instance:   instance,
		icon:       icon,
		cursor:     cursor,
		background: w.brushWindow,
		className:  windows.StringToUTF16Ptr("FA11yUpdaterWindow"),
		iconSmall:  icon,
	}
	class.size = uint32(unsafe.Sizeof(class))
	registerClassEx.Call(uintptr(unsafe.Pointer(&class)))

	const style = wsOverlapped | wsCaption | wsSysMenu | wsMinimizeBox
	width, height := 520, 372
	frame := rect{0, 0, int32(w.scale(width)), int32(w.scale(height))}
	adjustWindowRect.Call(uintptr(unsafe.Pointer(&frame)), style, 0, 0)
	cx, cy := int(frame.right-frame.left), int(frame.bottom-frame.top)
	screenW, _, _ := getSystemMetrics.Call(0)
	screenH, _, _ := getSystemMetrics.Call(1)
	current = w
	h, _, err := createWindowEx.Call(0, utf16("FA11yUpdaterWindow"), utf16(title), style,
		(screenW-uintptr(cx))/2, (screenH-uintptr(cy))/2, uintptr(cx), uintptr(cy), 0, 0, instance, 0)
	if h == 0 {
		return err
	}
	w.hwnd = h
	dark := uint32(1)
	dwmSetWindowAttr.Call(h, dwmaDarkMode, uintptr(unsafe.Pointer(&dark)), 4)

	// Controls are created in reading order: a screen reader names the log
	// from the static text just before it.
	w.title = w.child("STATIC", "FA11y Updater", ssNoPrefix, 0, 20, 14, 480, 32, 0)
	w.bar = w.child("msctls_progress32", "", pbsSmooth|pbsMarquee, 0, 20, 54, 480, 8, 0)
	w.status = w.child("STATIC", "Starting...", ssNoPrefix, 0, 20, 74, 480, 40, 0)
	w.logLabel = w.child("STATIC", "Log", ssNoPrefix, 0, 20, 124, 480, 20, 0)
	w.log = w.child("EDIT", "", esMultiline|esAutoVScroll|esReadOnly|esNoHideSel|wsVScroll|wsBorder|wsTabStop, 0, 20, 146, 480, 150, 0)
	w.button = w.child("BUTTON", "Close", bsPushButton|wsTabStop|wsDisabled, 0, 400, 310, 100, 34, idClose)
	for _, c := range []uintptr{w.status, w.logLabel, w.log, w.button} {
		sendMessage.Call(c, wmSetFont, w.fontText, 1)
	}
	sendMessage.Call(w.title, wmSetFont, w.fontTitle, 1)
	sendMessage.Call(w.log, emLimitText, 0x7FFFFFFE, 0)
	setWindowText.Call(w.bar, utf16("Update progress"))
	for _, c := range []uintptr{w.log, w.button} {
		setWindowTheme.Call(c, utf16("DarkMode_Explorer"), 0)
	}
	// An empty theme lets the bar take the colors below.
	setWindowTheme.Call(w.bar, utf16(""), utf16(""))
	sendMessage.Call(w.bar, pbmSetBarColor, 0, colorAccent)
	sendMessage.Call(w.bar, pbmSetBkColor, 0, colorTrack)
	w.setMarquee(true)

	showWindow.Call(h, swShow)
	setForeground.Call(h)
	setFocus.Call(w.log)
	return nil
}

// post runs fn on the window's thread, in order with earlier calls.
func (w *Window) post(fn func()) {
	w.mu.Lock()
	w.queue = append(w.queue, fn)
	w.mu.Unlock()
	postMessage.Call(w.hwnd, wmApp, 0, 0)
}

// call is post that waits for fn to finish, or for the window to close.
func (w *Window) call(fn func()) {
	done := make(chan struct{})
	w.post(func() { fn(); close(done) })
	select {
	case <-done:
	case <-w.closed:
	}
}

func (w *Window) drain() {
	w.mu.Lock()
	q := w.queue
	w.queue = nil
	w.mu.Unlock()
	for _, fn := range q {
		fn()
	}
}

func (w *Window) setMarquee(on bool) {
	style, _, _ := getWindowLongPtr.Call(w.bar, gwlStyle)
	if on {
		style |= pbsMarquee
	} else {
		style &^= pbsMarquee
	}
	setWindowLongPtr.Call(w.bar, gwlStyle, style)
	flag := uintptr(0)
	if on {
		flag = 1
	}
	sendMessage.Call(w.bar, pbmSetMarquee, flag, 30)
	w.marquee = on
}

// SetProgress shows percent (0 to 100) in the bar, or the moving marquee
// for a negative value, when the work has no known total.
func (w *Window) SetProgress(percent float64) {
	w.post(func() {
		if percent < 0 {
			if !w.marquee {
				w.setMarquee(true)
			}
			return
		}
		if w.marquee {
			w.setMarquee(false)
		}
		sendMessage.Call(w.bar, pbmSetPos, uintptr(min(percent, 100)+0.5), 0)
	})
}

// SetStatus replaces the status line and tells screen readers about it.
func (w *Window) SetStatus(text string, kind Kind) {
	w.post(func() {
		w.kind = kind
		setWindowText.Call(w.status, utf16(text))
		if kind == Failure {
			sendMessage.Call(w.bar, pbmSetBarColor, 0, colorDanger)
		}
		notifyWinEvent.Call(eventNameChange, w.status, objidClient, 0)
		notifyWinEvent.Call(eventLiveRegion, w.status, objidClient, 0)
	})
}

// Log appends a line to the log and moves the caret to its end, which a
// screen reader reading the focused log announces.
func (w *Window) Log(text string) {
	w.post(func() {
		if w.hasLog {
			text = "\r\n" + text
		}
		w.hasLog = true
		n, _, _ := getWindowTextLen.Call(w.log)
		sendMessage.Call(w.log, emSetSel, n, n)
		sendMessage.Call(w.log, emReplaceSel, 0, utf16(text))
		sendMessage.Call(w.log, emScrollCaret, 0, 0)
		notifyWinEvent.Call(eventValChange, w.log, objidClient, 0)
	})
}

// Finish enables the Close button, closes the window after closeAfter when
// that is positive, and waits until the window is closed.
func (w *Window) Finish(closeAfter time.Duration) {
	w.post(func() {
		w.finished = true
		enableWindow.Call(w.button, 1)
		w.setMarquee(false)
		sendMessage.Call(w.bar, pbmSetPos, 100, 0)
		if closeAfter > 0 {
			setTimer.Call(w.hwnd, timerClose, uintptr(closeAfter.Milliseconds()), 0)
		}
	})
	<-w.closed
}

// Hide takes the window off the screen, for when another process takes
// over, and waits until it is hidden.
func (w *Window) Hide() {
	w.call(func() { showWindow.Call(w.hwnd, swHide) })
}

// Ask shows a yes/no question and reports whether the answer was yes.
func (w *Window) Ask(question string) bool {
	yes := false
	w.call(func() {
		r, _, _ := messageBox.Call(w.hwnd, utf16(question), utf16("FA11y Updater"), mbYesNo|mbIconQuestion)
		yes = r == idYes
	})
	return yes
}

func wndProc(hwnd, message, wParam, lParam uintptr) uintptr {
	w := current
	switch message {
	case wmApp:
		w.drain()
		return 0
	case wmCommand:
		if id := wParam & 0xFFFF; id == idClose || id == idcCancel {
			w.requestClose()
		}
		return 0
	case wmClose:
		w.requestClose()
		return 0
	case wmTimer:
		killTimer.Call(hwnd, timerClose)
		destroyWindow.Call(hwnd)
		return 0
	case wmActivate:
		if wParam&0xFFFF == 0 {
			w.lastFocus, _, _ = getFocus.Call()
		} else if w.lastFocus != 0 {
			setFocus.Call(w.lastFocus)
		} else {
			setFocus.Call(w.log)
		}
		return 0
	case wmCtlColorDlg:
		return w.brushWindow
	case wmCtlColorStat, wmCtlColorEdit:
		// A read-only edit asks for its colors as a static does.
		text, back := uintptr(colorSecond), w.brushWindow
		backColor := uintptr(colorWindow)
		switch lParam {
		case w.log:
			text, back, backColor = colorText, w.brushCard, colorCard
		case w.title:
			text = colorText
		case w.logLabel:
			text = colorMuted
		case w.status:
			switch w.kind {
			case Success:
				text = colorSuccess
			case Failure:
				text = colorDanger
			}
		}
		setTextColor.Call(wParam, text)
		setBkColor.Call(wParam, backColor)
		return back
	case wmDestroy:
		postQuitMessage.Call(0)
		return 0
	}
	r, _, _ := defWindowProc.Call(hwnd, message, wParam, lParam)
	return r
}

// requestClose closes the window once the work is over. Before that the
// update must not be abandoned half way, so the request only leaves a note.
func (w *Window) requestClose() {
	if w.finished {
		destroyWindow.Call(w.hwnd)
		return
	}
	w.Log("Please wait. Close is available when the update has finished.")
}
