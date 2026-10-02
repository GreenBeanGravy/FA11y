package components

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"unsafe"

	"golang.org/x/sys/windows"

	"github.com/GreenBeanGravy/FA11y/installer/internal/manifest"
)

// Plan is what the elevated helper process installs. Writing every
// component into one plan means one UAC prompt covers all of them.
type Plan struct {
	FilesDir string             `json:"files_dir"`
	Items    []PlanItem         `json:"items"`
	Results  map[string]Outcome `json:"results,omitempty"`
}

type PlanItem struct {
	Component manifest.Component `json:"component"`
	File      string             `json:"file"`
}

// ErrCancelled means the user declined the UAC prompt.
var ErrCancelled = errors.New("the administrator prompt was declined")

// RunElevated writes plan to dir, starts exe elevated with
// "--elevated-plan <file>", waits, and returns the plan with results.
func RunElevated(exe, dir string, plan Plan) (Plan, error) {
	planPath := filepath.Join(dir, "elevated-plan.json")
	data, err := json.MarshalIndent(plan, "", "  ")
	if err != nil {
		return plan, err
	}
	if err := os.WriteFile(planPath, data, 0o644); err != nil {
		return plan, err
	}
	code, err := shellExecuteRunAs(exe, windows.EscapeArg("--elevated-plan")+" "+windows.EscapeArg(planPath))
	if err != nil {
		return plan, err
	}
	data, err = os.ReadFile(planPath)
	if err != nil {
		return plan, err
	}
	var done Plan
	if err := json.Unmarshal(data, &done); err != nil || done.Results == nil {
		return plan, errors.New("the elevated installer did not report results (exit code " + strconv.Itoa(code) + ")")
	}
	return done, nil
}

// RunPlan installs every item of the plan at planPath and writes the
// results back to it. It runs inside the elevated helper process.
func RunPlan(planPath string, say func(string, ...any)) error {
	data, err := os.ReadFile(planPath)
	if err != nil {
		return err
	}
	var plan Plan
	if err := json.Unmarshal(data, &plan); err != nil {
		return err
	}
	plan.Results = map[string]Outcome{}
	for _, item := range plan.Items {
		say("Installing %s...", item.Component.Name)
		out := Install(item.Component, item.File, plan.FilesDir)
		plan.Results[item.Component.ID] = out
		if out.OK {
			say("%s installed.", item.Component.Name)
		} else {
			say("%s failed: %s", item.Component.Name, out.Error)
		}
	}
	data, err = json.MarshalIndent(plan, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(planPath, data, 0o644)
}

type shellExecuteInfo struct {
	cbSize         uint32
	fMask          uint32
	hwnd           uintptr
	lpVerb         *uint16
	lpFile         *uint16
	lpParameters   *uint16
	lpDirectory    *uint16
	nShow          int32
	hInstApp       uintptr
	lpIDList       uintptr
	lpClass        *uint16
	hkeyClass      uintptr
	dwHotKey       uint32
	hIconOrMonitor uintptr
	hProcess       windows.Handle
}

const (
	seeMaskNoCloseProcess = 0x00000040
	seeMaskNoAsync        = 0x00000100
	swShowNormal          = 1
)

var procShellExecuteEx = windows.NewLazySystemDLL("shell32.dll").NewProc("ShellExecuteExW")

func shellExecuteRunAs(exe, params string) (int, error) {
	verb, _ := windows.UTF16PtrFromString("runas")
	file, _ := windows.UTF16PtrFromString(exe)
	args, _ := windows.UTF16PtrFromString(params)
	dir, _ := windows.UTF16PtrFromString(filepath.Dir(exe))
	info := shellExecuteInfo{
		fMask:        seeMaskNoCloseProcess | seeMaskNoAsync,
		lpVerb:       verb,
		lpFile:       file,
		lpParameters: args,
		lpDirectory:  dir,
		nShow:        swShowNormal,
	}
	info.cbSize = uint32(unsafe.Sizeof(info))
	ok, _, callErr := procShellExecuteEx.Call(uintptr(unsafe.Pointer(&info)))
	if ok == 0 {
		if errors.Is(callErr, windows.ERROR_CANCELLED) {
			return 0, ErrCancelled
		}
		return 0, callErr
	}
	defer windows.CloseHandle(info.hProcess)
	if _, err := windows.WaitForSingleObject(info.hProcess, windows.INFINITE); err != nil {
		return 0, err
	}
	var code uint32
	if err := windows.GetExitCodeProcess(info.hProcess, &code); err != nil {
		return 0, err
	}
	return int(code), nil
}
