import ctypes
from ctypes import wintypes
import time
import os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def send_maxscript(cmd_text: str) -> bool:
    """
    Sends a MaxScript command string to 3ds Max via its MXS_Scintilla mini-listener window.
    Works seamlessly across desktop sessions and processes.
    """
    try:
        hDesk = user32.OpenInputDesktop(0, False, 0x10000000)
        if not hDesk:
            hDesk = user32.OpenDesktopW('Default', 0, False, 0x10000000)
        if hDesk:
            user32.SetThreadDesktop(hDesk)
    except Exception:
        pass

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    max_hwnds = []

    def enum_cb(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            if "Autodesk 3ds Max" in title or "3ds Max" in title:
                max_hwnds.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

    # Fallback to process check if window title did not match
    if not max_hwnds:
        try:
            import psutil
            max_pids = set()
            for p in psutil.process_iter(['pid', 'name']):
                if p.info['name'] and '3dsmax' in p.info['name'].lower():
                    max_pids.add(p.info['pid'])

            if max_pids:
                def enum_pid_cb(hwnd, lparam):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value in max_pids:
                        max_hwnds.append(hwnd)
                    return True
                user32.EnumWindows(WNDENUMPROC(enum_pid_cb), 0)
        except Exception:
            pass

    if not max_hwnds:
        return False

    scintillas = []
    def child_cb(hwnd, lparam):
        buf_cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf_cls, 256)
        if buf_cls.value == "MXS_Scintilla":
            scintillas.append(hwnd)
        return True

    for m_hwnd in max_hwnds:
        if user32.IsIconic(m_hwnd):
            user32.ShowWindow(m_hwnd, 9)  # SW_RESTORE
        user32.EnumChildWindows(m_hwnd, WNDENUMPROC(child_cb), 0)
        if scintillas:
            break

    if not scintillas:
        return False

    # Choose the bottom-most mini-listener command input box
    best_target = None
    max_y = -999999
    for h in scintillas:
        rect = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(rect))
        if rect.top > max_y:
            max_y = rect.top
            best_target = h

    if best_target is None:
        return False

    WM_SETTEXT = 0x000C
    WM_CHAR = 0x0102
    VK_RETURN = 0x0D

    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_wchar_p]
    user32.SendMessageW.restype = wintypes.LPARAM
    user32.SendMessageW(best_target, WM_SETTEXT, 0, cmd_text)

    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW(best_target, WM_CHAR, VK_RETURN, 0)
    return True


def run_ms_file(file_path: str) -> bool:
    """
    Executes a .ms script file in 3ds Max via fileIn command.
    """
    clean_path = os.path.abspath(file_path).replace("\\", "/")
    cmd = f'fileIn "{clean_path}"\r\n'
    return send_maxscript(cmd)
