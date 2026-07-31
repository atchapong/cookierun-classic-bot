import win32gui, win32con, time, threading, random
from ppadb.client import Client as AdbClient

# ในไฟล์ controller.py
class ControllerBot:
    def __init__(self):
        self.client = AdbClient(host="127.0.0.1", port=5037)
        self.device = None

    def connect_device(self, serial_name):
        try:
            self.device = self.client.device(serial_name)
            if self.device:
                return True
            return False
        except Exception:
            return False

    def get_emulator_windows(self):
        windows = []
        def enum_proc(hwnd, lParam):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                cls_name = win32gui.GetClassName(hwnd)
                if title and ("LDPlayer" in title or cls_name in ["LDPlayerMainFrame", "dnplayer_class"]):
                    windows.append(title)
            return True
        win32gui.EnumWindows(enum_proc, None)
        return sorted(list(set(windows)))

    def scan_devices(self):
        try:
            self.adb_client = AdbClient(host="127.0.0.1", port=5037)
            self.device_list = sorted(self.adb_client.devices(), key=lambda d: d.serial)
            return len(self.device_list) > 0
        except: return False

    def connect_device(self, index=0):
        try:
            if not self.device_list or index >= len(self.device_list): return False
            self.adb_device = self.device_list[index]
            size_str = self.adb_device.shell("wm size")
            if "Physical size:" in size_str:
                w, h = size_str.replace("Physical size:", "").strip().split("x")
                self.adb_w, self.adb_h = int(w), int(h)
            return True
        except: return False

    def get_child_windows(self, main_hwnd):
        childs = []
        def enum_child(hwnd, lst):
            lst.append(hwnd)
            return True
        win32gui.EnumChildWindows(main_hwnd, enum_child, childs)
        return childs

    def click(self, x, y, frame_w, frame_h):
        if not self.adb_device: return
        jx, jy = random.randint(-15, 15), random.randint(-15, 15)
        rx = max(0, min(int(((x + jx) / frame_w) * self.adb_w), self.adb_w))
        ry = max(0, min(int(((y + jy) / frame_h) * self.adb_h), self.adb_h))
        self.adb_device.shell(f"input tap {rx} {ry}")

    # 🎯 BUGFIX: เพิ่มการรับค่า key_code เพื่อให้เลือกปุ่มที่จะกดได้!
    def jump(self, child_windows, key_code=0x26):
        def human_keypress():
            for sub in child_windows: win32gui.PostMessage(sub, win32con.WM_KEYDOWN, key_code, 0)
            time.sleep(random.uniform(0.03, 0.15))
            for sub in child_windows: win32gui.PostMessage(sub, win32con.WM_KEYUP, key_code, 0)
        threading.Thread(target=human_keypress, daemon=True).start()