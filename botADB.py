import win32gui, win32ui, win32con, cv2, numpy as np, time, threading, os, sys, winsound, random
import customtkinter as ctk 
from PIL import Image, ImageTk
from ppadb.client import Client as AdbClient
import ctypes

try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    try: ctypes.windll.user32.SetProcessDPIAware()
    except: pass

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

bot_running = False
jump_mode = "Auto Jump"
program_closing = False
target_window_name = "" 
TEMPLATE_BASE_WIDTH = 1600.0  
cached_templates = {}         
adb_client = None
adb_device = None
adb_w, adb_h = 1280, 720
adb_device_list = [] 

def resource_path(relative_path):
    try: base_path = sys._MEIPASS
    except Exception: base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def get_emulator_windows():
    windows = []
    def enum_windows_proc(hwnd, lParam):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            cls_name = win32gui.GetClassName(hwnd)
            if title and ("LDPlayer" in title or cls_name in ["LDPlayerMainFrame", "dnplayer_class"]):
                windows.append(title)
        return True
    win32gui.EnumWindows(enum_windows_proc, None)
    return sorted(list(set(windows))) 

def refresh_all_devices():
    global adb_client, target_window_name, adb_device_list
    win_list = get_emulator_windows()
    window_combo.configure(values=win_list if win_list else [""])
    if win_list:
        window_combo.set(win_list[0])
        target_window_name = window_combo.get().strip()
    else:
        window_combo.set('')
        target_window_name = ""
    try:
        adb_client = AdbClient(host="127.0.0.1", port=5037)
        adb_device_list = sorted(adb_client.devices(), key=lambda d: d.serial)
        if win_list: log_to_gui(f"🔄 สแกนพบจอเกม {len(win_list)} จอ")
        else: log_to_gui("❌ ไม่พบจอเกม (กรุณาเปิด LDPlayer ก่อนสแกน)")
        
        if connect_adb_auto():
            adb_status_badge.configure(text="✅ เชื่อมต่อแล้ว", fg_color="#2ecc71")
        else:
            adb_status_badge.configure(text="❌ ไม่พบอุปกรณ์", fg_color="#e74c3c")
    except Exception:
        adb_status_badge.configure(text="❌ ADB SERVER DOWN", fg_color="#e74c3c")
        log_to_gui(f"❌ ADB Server ยังไม่เปิด")

def connect_adb_auto():
    global adb_device, adb_w, adb_h
    try:
        if not adb_device_list: return False
        current_val = window_combo.get()
        all_vals = window_combo.cget("values")
        selected_index = all_vals.index(current_val) if current_val in all_vals else 0
        if selected_index < 0 or selected_index >= len(adb_device_list): selected_index = 0 
        adb_device = adb_device_list[selected_index]
        size_str = adb_device.shell("wm size")
        if "Physical size:" in size_str:
            w, h = size_str.replace("Physical size:", "").strip().split("x")
            adb_w, adb_h = int(w), int(h)
        return True
    except Exception: return False

def adb_click(x, y, frame_w, frame_h):
    if not adb_device: return
    jitter_x, jitter_y = random.randint(-15, 15), random.randint(-15, 15)
    real_x = max(0, min(int(((x + jitter_x) / frame_w) * adb_w), adb_w))
    real_y = max(0, min(int(((y + jitter_y) / frame_h) * adb_h), adb_h))
    adb_device.shell(f"input tap {real_x} {real_y}")

def get_inner_windows(hwnd, window_list):
    window_list.append(hwnd)
    return True

def capture_background_autosize(hwnd):
    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        width, height = right - left, bottom - top
        if width <= 0 or height <= 0: return None, 1280, 720
        wDC = win32gui.GetWindowDC(hwnd)
        dcObj = win32ui.CreateDCFromHandle(wDC)
        cDC = dcObj.CreateCompatibleDC()
        dataBitMap = win32ui.CreateBitmap()
        dataBitMap.CreateCompatibleBitmap(dcObj, width, height)
        cDC.SelectObject(dataBitMap)
        cDC.BitBlt((0, 0), (width, height), dcObj, (0, 0), win32con.SRCCOPY)
        signedIntsArray = dataBitMap.GetBitmapBits(True)
        img = np.frombuffer(signedIntsArray, dtype='uint8')
        img.shape = (height, width, 4)
        win32gui.DeleteObject(dataBitMap.GetHandle())
        cDC.DeleteDC()
        dcObj.DeleteDC()
        win32gui.ReleaseDC(hwnd, wDC)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR), width, height
    except: return None, 1280, 720

def send_key(windows, key_code):
    def human_keypress():
        for sub_hwnd in windows: win32gui.PostMessage(sub_hwnd, win32con.WM_KEYDOWN, key_code, 0)
        time.sleep(random.uniform(0.03, 0.15))
        for sub_hwnd in windows: win32gui.PostMessage(sub_hwnd, win32con.WM_KEYUP, key_code, 0)
    threading.Thread(target=human_keypress, daemon=True).start()

def preload_and_resize_templates(current_screen_width):
    global cached_templates
    scale = current_screen_width / TEMPLATE_BASE_WIDTH
    image_list = [
        "id_surprise.png", "id_result.png", "id_item.png", "btn_confirm.png", 
        "id_lobby.png", "btn_play.png", "btn_ok.png", "id_playing.png", 
        "item_boost.png", "item_relay.png", "btn_open_all.png", "btn_mystery_box_confirm.png",
        "buff_coin.png", "red_box.png", "btn_multi.png", "btn_multi_buy.png", 
        "crystal_warning.png", "btn_cancel.png" 
    ]
    log_to_gui(f"🔄 กำลังโหลดรูปภาพ (Scale: {scale:.2f})...")
    cached_templates.clear() 
    for img_name in image_list:
        path = resource_path(img_name) 
        if os.path.exists(path):
            img = cv2.imread(path)
            new_w, new_h = int(img.shape[1] * scale), int(img.shape[0] * scale)
            cached_templates[img_name] = cv2.resize(img, (new_w, new_h))

def find_image_in_zone(main_frame, template_name, crop_limits, threshold=0.70):
    if template_name not in cached_templates: return None
    template = cached_templates[template_name]
    h, w = template.shape[:2]
    h_max, w_max = main_frame.shape[:2]
    y1, y2 = int(h_max * crop_limits[0]), int(h_max * crop_limits[1])
    x1, x2 = int(w_max * crop_limits[2]), int(w_max * crop_limits[3])
    zone_frame = main_frame[y1:y2, x1:x2]
    if zone_frame.shape[0] < h or zone_frame.shape[1] < w: return None
    result = cv2.matchTemplate(zone_frame, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold: return (x1 + max_loc[0] + int(w / 2), y1 + max_loc[1] + int(h / 2))
    return None

def find_green_button_center(main_frame, crop_limits):
    h_max, w_max = main_frame.shape[:2]
    y1, y2 = int(h_max * crop_limits[0]), int(h_max * crop_limits[1])
    x1, x2 = int(w_max * crop_limits[2]), int(w_max * crop_limits[3])
    zone_frame = main_frame[y1:y2, x1:x2]
    hsv = cv2.cvtColor(zone_frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([35, 120, 120]), np.array([85, 255, 255]))
    if cv2.countNonZero(mask) > (zone_frame.shape[0] * zone_frame.shape[1] * 0.03):
        M = cv2.moments(mask)
        if M["m00"] != 0: return (x1 + int(M["m10"] / M["m00"]), y1 + int(M["m01"] / M["m00"]))
    return None

def solve_captcha_logic(frame):
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        card_rects = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if 100 < w < 300 and 150 < h < 400 and 0.5 < (w/h) < 0.9:
                card_rects.append((x, y, w, h))
        if len(card_rects) < 3: return None
        scores = [0] * len(card_rects)
        for i in range(len(card_rects)):
            x, y, w, h = card_rects[i]
            roi1 = frame[y:y+h, x:x+w]
            hist1 = cv2.calcHist([roi1], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            cv2.normalize(hist1, hist1)
            for j in range(len(card_rects)):
                if i != j:
                    jx, jy, jw, jh = card_rects[j]
                    roi2 = frame[jy:jy+jh, jx:jx+jw]
                    hist2 = cv2.calcHist([roi2], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                    cv2.normalize(hist2, hist2)
                    scores[i] += cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
        odd_idx = np.argmin(scores)
        odd_x, odd_y, odd_w, odd_h = card_rects[odd_idx]
        return (odd_x + (odd_w // 2), odd_y + (odd_h // 2))
    except Exception: return None

def check_current_page_by_image(frame):
    if find_image_in_zone(frame, "id_surprise.png", [0.0, 0.20, 0.2, 0.8], threshold=0.70): return "SURPRISE_CAPTCHA"
    if find_image_in_zone(frame, "crystal_warning.png", [0.2, 0.8, 0.2, 0.8], threshold=0.75): return "CRYSTAL_WARNING_POPUP"
    if find_image_in_zone(frame, "btn_multi_buy.png", [0.6, 1.0, 0.2, 0.8], threshold=0.75): return "MULTI_BUY_PAGE"
    if find_image_in_zone(frame, "btn_open_all.png", [0.70, 0.95, 0.35, 0.65], threshold=0.75): return "MYSTERY_BOX_MAIN_PAGE"
    if find_image_in_zone(frame, "btn_mystery_box_confirm.png", [0.75, 0.95, 0.40, 0.60], threshold=0.75): return "MYSTERY_BOX_CONFIRM_PAGE"
    if find_image_in_zone(frame, "id_result.png", [0.0, 0.25, 0.3, 0.7], threshold=0.70): return "RESULT_PAGE"
    if enable_item_page_var.get() and find_image_in_zone(frame, "id_item.png", [0.0, 0.25, 0.05, 0.5], threshold=0.70): return "ITEM_PAGE"
    if find_image_in_zone(frame, "id_lobby.png", [0.0, 0.4, 0.0, 1.0], threshold=0.70): return "LOBBY_PAGE"
    if find_image_in_zone(frame, "item_boost.png", [0.0, 1.0, 0.0, 1.0], threshold=0.60): return "BOOST_POPUP"
    if find_image_in_zone(frame, "item_relay.png", [0.0, 1.0, 0.0, 1.0], threshold=0.60): return "RELAY_POPUP"
    if find_image_in_zone(frame, "id_playing.png", [0.0, 0.20, 0.0, 1.0], threshold=0.70): return "PLAYING_GAME"
    if find_green_button_center(frame, [0.65, 0.95, 0.20, 0.80]): return "ANY_CONFIRM_POPUP"
    return "UNKNOWN_OR_LOADING"

def log_to_gui(message):
    timestamp = time.strftime("[%H:%M:%S] ")
    log_box.configure(state="normal")
    log_box.insert("end", timestamp + message + "\n")
    log_box.see("end")
    log_box.configure(state="disabled")

def video_preview_worker():
    global program_closing, target_window_name
    while not program_closing:
        time.sleep(0.03)  
        if not show_preview_var.get():
            video_label.configure(image="", text="🙈 ปิดพรีวิวเพื่อประหยัดสเปก", text_color="gray")
            time.sleep(0.5)
            continue
        if not target_window_name: continue
        main_hwnd = win32gui.FindWindow(None, target_window_name)
        if main_hwnd == 0: continue
        child_windows = []
        win32gui.EnumChildWindows(main_hwnd, get_inner_windows, child_windows)
        if not child_windows: continue
        frame, _, _ = capture_background_autosize(child_windows[-1])
        if frame is None: continue
        cv2_resized = cv2.resize(frame, (480, 270))  
        cv2_rgb = cv2.cvtColor(cv2_resized, cv2.COLOR_BGR2RGB)
        img_tk = ctk.CTkImage(light_image=Image.fromarray(cv2_rgb), dark_image=Image.fromarray(cv2_rgb), size=(480, 270))
        video_label.configure(image=img_tk, text="")

def bot_worker():
    global bot_running, jump_mode, target_window_name
    main_hwnd = win32gui.FindWindow(None, target_window_name)
    if main_hwnd == 0:
        log_to_gui(f"❌ ระบบภาพล้มเหลว: ไม่พบจอ '{target_window_name}'")
        stop_bot()
        return

    child_windows = []
    win32gui.EnumChildWindows(main_hwnd, get_inner_windows, child_windows)
    if child_windows:
        _, screen_w, _ = capture_background_autosize(child_windows[-1])
        preload_and_resize_templates(screen_w)
        
    last_jump_time, next_click_allowed_time, last_scan_time = 0, 0, 0
    last_action_time = time.time()
    current_page, last_logged_page = "UNKNOWN_OR_LOADING", ""
    
    try: min_d, max_d = float(min_delay_var.get()), float(max_delay_var.get())
    except: min_d, max_d = 8.0, 10.0
    
    log_to_gui(f"🤖 บอทพร้อมทำงานเป้าหมาย: {target_window_name}")
    
    while bot_running:
        time.sleep(0.016)
        child_windows = []
        win32gui.EnumChildWindows(main_hwnd, get_inner_windows, child_windows)
        if not child_windows: continue
        target_hwnd = child_windows[-1]
        
        frame, width, height = capture_background_autosize(target_hwnd)
        if frame is None: continue
        
        current_time = time.time()
        scan_delay = 0.1 if current_page == "UNKNOWN_OR_LOADING" else 0.5  
        
        if current_time - last_scan_time >= scan_delay:
            last_scan_time = current_time
            current_page = check_current_page_by_image(frame)
                
        # 🎯 ล้างเวลาหน่วงทิ้งทันที ถ้าจอเปลี่ยนเป็นป๊อปอัปด่วน
        if current_page != last_logged_page and current_page != "UNKNOWN_OR_LOADING":
            log_to_gui(f"🖥️ สถานะจอ: {current_page}")
            last_logged_page = current_page
            if current_page in ["BOOST_POPUP", "RELAY_POPUP", "ANY_CONFIRM_POPUP", "SURPRISE_CAPTCHA", "CRYSTAL_WARNING_POPUP"]:
                next_click_allowed_time = 0.0 
                
        # 🎯 🌟 SMART SENSOR: เช็กว่าหมุนกาชาเสร็จก่อนกำหนดหรือยัง (ทำงานตลอดเวลา)
        if current_page == "ITEM_PAGE" and auto_gacha_var.get():
            # ถ้าคิวรอยังเหลือเยอะเกิน 3 วินาที (แปลว่ากำลังติด Do Not Disturb รอหมุนกาชาอยู่)
            if next_click_allowed_time > current_time + 3.0:
                # ลองแอบส่องว่าได้บัฟหรือยัง
                if find_image_in_zone(frame, "buff_coin.png", [0.4, 0.9, 0.2, 0.8], threshold=0.75):
                    log_to_gui("⚡ สุ่มเสร็จแล้ว! (เจอบัฟเป้าหมาย) ยกเลิกการรอคอย เข้าเกมทันที!")
                    next_click_allowed_time = 0.0 # ฉีกสัญญาเวลาทิ้ง ให้ทำลอจิกบรรทัดล่างสุดทันที
            
        if current_page == "PLAYING_GAME":
            last_action_time = current_time 
            if jump_mode == "Auto Jump":
                if current_time - last_jump_time > random.uniform(0.55, 0.85):
                    send_key(child_windows, 0x26)
                    last_jump_time = current_time
            elif jump_mode == "Jelly Hunter":
                roi = frame[int(height * 0.40):int(height * 0.65), int(width * 0.38):int(width * 0.48)]
                hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                mask_y = cv2.inRange(hsv_roi, np.array([15, 100, 100]), np.array([35, 255, 255]))
                mask_p = cv2.inRange(hsv_roi, np.array([140, 50, 50]), np.array([170, 255, 255]))
                if np.sum(cv2.bitwise_or(mask_y, mask_p) > 0) > 80:
                    if current_time - last_jump_time > random.uniform(0.65, 0.85):
                        send_key(child_windows, 0x26)
                        last_jump_time = current_time
                        
        elif current_page == "SURPRISE_CAPTCHA":
            log_to_gui("🔍 กำลังวิเคราะห์หาการ์ดที่แปลกพวก (Captcha)...")
            time.sleep(1.0) 
            fresh_frame, w, h = capture_background_autosize(target_hwnd)
            target_pt = solve_captcha_logic(fresh_frame)
            if target_pt:
                adb_click(target_pt[0], target_pt[1], w, h)
                log_to_gui(f"🎯 แก้สกรีนดักบอทสำเร็จ! จิ้มพิกัด: {target_pt}")
            else:
                log_to_gui("⚠️ ระบบวิเคราะห์พลาด รอแก้ด้วยมือ...")
                winsound.Beep(2000, 300)
            last_action_time, next_click_allowed_time = time.time(), time.time() + 2.0

        elif current_page == "BOOST_POPUP":
            if use_boost_var.get():
                match_loc = find_image_in_zone(frame, "item_boost.png", [0.0, 1.0, 0.0, 1.0], threshold=0.60)
                if match_loc:
                    adb_click(match_loc[0], match_loc[1], width, height)
                    log_to_gui("🚀 ตรวจพบ บูสเตอร์ -> กดใช้งานด่วน!")
                else:
                    adb_click(int(width * 0.50), int(height * 0.50), width, height)
            else:
                adb_click(int(width * 0.78), int(height * 0.25), width, height)
                log_to_gui("🚫 ข้ามหน้าต่าง บูสเตอร์ด่วน")
            last_action_time = current_time
            next_click_allowed_time = current_time + 0.1 

        elif current_page == "RELAY_POPUP":
            if use_relay_var.get():
                match_loc = find_image_in_zone(frame, "item_relay.png", [0.0, 1.0, 0.0, 1.0], threshold=0.60)
                if match_loc:
                    adb_click(match_loc[0], match_loc[1], width, height)
                    log_to_gui("🔄 ตรวจพบ ตัวผลัด -> กดใช้งานด่วน!")
                else:
                    adb_click(int(width * 0.50), int(height * 0.50), width, height)
            else:
                adb_click(int(width * 0.78), int(height * 0.25), width, height)
                log_to_gui("🚫 ข้ามหน้าต่าง ตัวผลัดด่วน")
            last_action_time = current_time
            next_click_allowed_time = current_time + 0.1 
            
        elif current_time >= next_click_allowed_time:
            try: min_d, max_d = float(min_delay_var.get()), float(max_delay_var.get())
            except: min_d, max_d = 8.0, 10.0
            random_wait = random.uniform(min_d, max_d)
            
            if current_time - last_action_time >= 15.0:
                if current_page != "UNKNOWN_OR_LOADING":
                    log_to_gui(f"⚔️ [Anti-Stuck] รีเฟรชหน้า {current_page}")
                    if current_page in ["LOBBY_PAGE", "ITEM_PAGE"]: adb_click(int(width * 0.78), int(height * 0.86), width, height)
                    elif current_page in ["ANY_CONFIRM_POPUP", "MYSTERY_BOX_MAIN_PAGE", "MYSTERY_BOX_CONFIRM_PAGE", "MULTI_BUY_PAGE", "CRYSTAL_WARNING_POPUP"]: adb_click(int(width * 0.50), int(height * 0.79), width, height)
                    elif current_page == "RESULT_PAGE": adb_click(int(width * 0.35), int(height * 0.82), width, height)
                last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                continue

            if current_page == "LOBBY_PAGE":
                play_match = find_image_in_zone(frame, "btn_play.png", [0.70, 0.95, 0.60, 0.95], threshold=0.65)
                if play_match: 
                    adb_click(play_match[0], play_match[1], width, height)
                    log_to_gui(f"🏡 Lobby -> กด Play (หน่วง {random_wait:.1f} วิ)")
                    last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                    
            elif current_page == "ITEM_PAGE":
                if auto_gacha_var.get():
                    coin_buff_match = find_image_in_zone(frame, "buff_coin.png", [0.4, 0.9, 0.2, 0.8], threshold=0.75)
                    if coin_buff_match:
                        log_to_gui("🎉 มีบัฟเป้าหมายแล้ว! -> เตรียมตัววิ่ง...")
                        play_match = find_image_in_zone(frame, "btn_play.png", [0.70, 0.95, 0.60, 0.95], threshold=0.65)
                        if play_match: 
                            adb_click(play_match[0], play_match[1], width, height)
                        else:
                            adb_click(int(width * 0.82), int(height * 0.85), width, height)
                            log_to_gui("▶️ บังคับจิ้มเข้าเกม (มุมขวาล่าง)")
                        last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                    else:
                        multi_btn = find_image_in_zone(frame, "btn_multi.png", [0.3, 0.9, 0.5, 1.0], threshold=0.70)
                        if multi_btn:
                            adb_click(multi_btn[0], multi_btn[1], width, height)
                            log_to_gui(f"🎰 เปิดหน้า Multi-Buy... (หน่วง {random_wait:.1f} วิ)")
                            last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                        else:
                            red_box = find_image_in_zone(frame, "red_box.png", [0.3, 0.9, 0.2, 0.8], threshold=0.70)
                            if red_box:
                                adb_click(red_box[0], red_box[1], width, height)
                                log_to_gui("📦 โฟกัสไปที่กล่องแดง...")
                            else:
                                adb_click(int(width * 0.82), int(height * 0.55), width, height)
                            last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                else:
                    play_match = find_image_in_zone(frame, "btn_play.png", [0.70, 0.95, 0.60, 0.95], threshold=0.65)
                    if play_match: 
                        adb_click(play_match[0], play_match[1], width, height)
                        log_to_gui(f"🎒 Item -> กดเข้าด่าน (หน่วง {random_wait:.1f} วิ)")
                    else: adb_click(int(width * 0.82), int(height * 0.85), width, height)
                    last_action_time, next_click_allowed_time = current_time, current_time + random_wait

            elif current_page == "MULTI_BUY_PAGE":
                multi_buy_btn = find_image_in_zone(frame, "btn_multi_buy.png", [0.6, 1.0, 0.2, 0.8], threshold=0.75)
                if multi_buy_btn:
                    adb_click(multi_buy_btn[0], multi_buy_btn[1], width, height)
                    # 🎯 ล็อกเวลาพักยาวๆ 90 วินาที ให้เกมได้หมุนสบายๆ
                    log_to_gui("💸 กด Multi-Buy สุ่มรัวๆ! (เผื่อเวลาให้หมุนสูงสุด 90 วิ...)")
                    last_action_time = current_time
                    next_click_allowed_time = current_time + 90.0
                else: 
                    log_to_gui("⚠️ หาปุ่ม Multi-Buy ไม่เจอ")
                    last_action_time = current_time
                    next_click_allowed_time = current_time + random_wait

            elif current_page == "CRYSTAL_WARNING_POPUP":
                log_to_gui("⚠️ ตรวจพบเงินหมด! ปิดสวิตช์ Multi-Buy อัตโนมัติ เพื่อเซฟคริสตัลไอดี")
                log_to_gui(f"🔄 กำลังกดยกเลิกเพื่อปล่อยคุกกี้เข้าเล่นเกมตาปกติ... (หน่วง {random_wait:.1f} วิ)")
                auto_gacha_var.set(False)
                cancel_match = find_image_in_zone(frame, "btn_cancel.png", [0.4, 0.9, 0.2, 0.8], threshold=0.70)
                if cancel_match: adb_click(cancel_match[0], cancel_match[1], width, height)
                else: adb_click(int(width * 0.42), int(height * 0.62), width, height)
                last_action_time, next_click_allowed_time = current_time, current_time + random_wait

            elif current_page == "MYSTERY_BOX_MAIN_PAGE":
                match_loc = find_image_in_zone(frame, "btn_open_all.png", [0.70, 0.95, 0.35, 0.65], threshold=0.75)
                if match_loc:
                    adb_click(match_loc[0], match_loc[1], width, height)
                    log_to_gui(f"🎁 กดเปิดกล่องทั้งหมด (หน่วง {random_wait:.1f} วิ)")
                    last_action_time, next_click_allowed_time = current_time, current_time + random_wait

            elif current_page == "MYSTERY_BOX_CONFIRM_PAGE":
                match_loc = find_image_in_zone(frame, "btn_mystery_box_confirm.png", [0.75, 0.95, 0.40, 0.60], threshold=0.75)
                if match_loc:
                    adb_click(match_loc[0], match_loc[1], width, height)
                    log_to_gui(f"🎁 กดยืนยันรับกล่อง (หน่วง {random_wait:.1f} วิ)")
                    last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                    
            elif current_page == "ANY_CONFIRM_POPUP":
                green_btn = find_green_button_center(frame, [0.65, 0.95, 0.20, 0.80])
                if green_btn:
                    confirm_match = find_image_in_zone(frame, "btn_confirm.png", [0.65, 0.95, 0.20, 0.80], threshold=0.60)
                    if confirm_match: adb_click(confirm_match[0], confirm_match[1], width, height)
                    else: adb_click(green_btn[0], green_btn[1], width, height)
                    log_to_gui(f"✅ กดปุ่มยืนยัน/สีเขียว (หน่วง {random_wait:.1f} วิ)")
                else: adb_click(int(width * 0.50), int(height * 0.79), width, height)
                last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                    
            elif current_page == "RESULT_PAGE":
                ok_match = find_image_in_zone(frame, "btn_ok.png", [0.70, 0.95, 0.20, 0.50], threshold=0.75)
                if ok_match: 
                    result_wait = random.uniform(6.0, 7.5)
                    log_to_gui(f"🏆 ตรวจพบหน้าสรุปผล -> หน่วง {result_wait:.1f} วิ...")
                    time.sleep(result_wait)
                    frame, width, height = capture_background_autosize(target_hwnd)
                    ok_match = find_image_in_zone(frame, "btn_ok.png", [0.70, 0.95, 0.20, 0.50], threshold=0.75)
                    if ok_match: adb_click(ok_match[0], ok_match[1], width, height)
                    last_action_time, next_click_allowed_time = time.time(), time.time() + random_wait

def start_bot():
    global bot_running, jump_mode, target_window_name
    try:
        min_d, max_d = float(min_delay_var.get()), float(max_delay_var.get())
        if min_d > max_d:
            log_to_gui("❌ หน่วงเวลา Min ต้องน้อยกว่า Max!")
            return
    except:
        log_to_gui("❌ กรอกตัวเลขหน่วงเวลาให้ถูกต้อง!")
        return

    if not bot_running:
        target_window_name = window_combo.get().strip()
        if not target_window_name:
            log_to_gui("❌ เลือกจอเกมก่อนเริ่มงาน!")
            return
        if not connect_adb_auto(): 
            log_to_gui("❌ ล้มเหลว: กรุณากดปุ่มสแกนจอก่อน")
            return
        bot_running = True
        jump_mode = mode_combo.get()
        status_label.configure(text=f"🟢 STATUS: WORKING", text_color="#2ecc71")
        btn_start.configure(state="disabled", fg_color="gray")
        btn_stop.configure(state="normal", fg_color="#e74c3c")
        threading.Thread(target=bot_worker, daemon=True).start()

def stop_bot():
    global bot_running
    bot_running = False
    status_label.configure(text="🔴 STATUS: STOPPED", text_color="#e74c3c")
    btn_start.configure(state="normal", fg_color="#3498db")
    btn_stop.configure(state="disabled", fg_color="gray")
    log_to_gui("⏹ หยุดการทำงาน")

def on_closing():
    global program_closing, bot_running
    program_closing, bot_running = True, False
    root.destroy()

root = ctk.CTk()
root.title("Cookie Run AI Bot - Ultimate Auto Farm V42.6 (Smart Sensor)")
root.geometry("920x620")
root.resizable(False, False)
root.protocol("WM_DELETE_WINDOW", on_closing)

show_preview_var = ctk.BooleanVar(value=True)
enable_item_page_var = ctk.BooleanVar(value=True)
use_boost_var = ctk.BooleanVar(value=True)       
use_relay_var = ctk.BooleanVar(value=True)       
auto_gacha_var = ctk.BooleanVar(value=True) 

min_delay_var = ctk.StringVar(value="8.0")
max_delay_var = ctk.StringVar(value="10.0")

left_panel = ctk.CTkFrame(root, corner_radius=10)
left_panel.pack(side="left", fill="both", expand=True, padx=(10,5), pady=10)
right_panel = ctk.CTkFrame(root, corner_radius=10, width=300)
right_panel.pack(side="right", fill="y", padx=(5,10), pady=10)

video_label = ctk.CTkLabel(left_panel, text="📺 กำลังเชื่อมต่อภาพ...", width=480, height=270, fg_color="black", corner_radius=10)
video_label.pack(pady=10, padx=10)

control_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
control_frame.pack(fill="x", padx=10, pady=5)
ctk.CTkLabel(control_frame, text="🎯 เลือกจอ:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
window_combo = ctk.CTkComboBox(control_frame, width=180, values=[])
window_combo.grid(row=0, column=1, padx=5, pady=5)
ctk.CTkButton(control_frame, text="🔄 สแกนจอ", command=refresh_all_devices, width=90).grid(row=0, column=2, padx=5, pady=5)

adb_status_badge = ctk.CTkLabel(control_frame, text="⚪ รอการสแกน", font=("Helvetica", 11, "bold"), fg_color="gray", text_color="white", corner_radius=6, width=100, height=28)
adb_status_badge.grid(row=0, column=3, padx=5, pady=5)

ctk.CTkLabel(control_frame, text="⏳ หน่วงเวลา (วิ):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
delay_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
delay_frame.grid(row=1, column=1, columnspan=2, sticky="w")
ctk.CTkEntry(delay_frame, textvariable=min_delay_var, width=50).pack(side="left", padx=2)
ctk.CTkLabel(delay_frame, text="-").pack(side="left")
ctk.CTkEntry(delay_frame, textvariable=max_delay_var, width=50).pack(side="left", padx=2)

switch_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
switch_frame.pack(fill="x", padx=10, pady=5)
ctk.CTkSwitch(switch_frame, text="👁️ พรีวิวภาพจอ", variable=show_preview_var).grid(row=0, column=0, padx=10, pady=5, sticky="w")
ctk.CTkSwitch(switch_frame, text="🎒 แวะหน้าไอเทม", variable=enable_item_page_var).grid(row=0, column=1, padx=10, pady=5, sticky="w")
ctk.CTkSwitch(switch_frame, text="🚀 ใช้บูสเตอร์ด่าน", variable=use_boost_var).grid(row=1, column=0, padx=10, pady=5, sticky="w")
ctk.CTkSwitch(switch_frame, text="🔄 ใช้คุกกี้ตัวผลัด", variable=use_relay_var).grid(row=1, column=1, padx=10, pady=5, sticky="w")
ctk.CTkSwitch(switch_frame, text="🎰 ออโต้ Multi-Buy", variable=auto_gacha_var).grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="w")

status_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
status_frame.pack(fill="x", padx=10, pady=5)
status_label = ctk.CTkLabel(status_frame, text="🔴 STATUS: STOPPED", font=("Helvetica", 14, "bold"), text_color="#e74c3c")
status_label.pack(side="left", padx=10)
mode_combo = ctk.CTkComboBox(status_frame, values=["Jelly Hunter", "Auto Jump", "No Jump"], width=130)
mode_combo.pack(side="right", padx=10)
mode_combo.set("Auto Jump")

btn_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
btn_frame.pack(fill="x", side="bottom", pady=10)
btn_start = ctk.CTkButton(btn_frame, text="▶ START BOT", command=start_bot, font=("Helvetica", 14, "bold"), fg_color="#3498db", height=40)
btn_start.pack(side="left", fill="x", expand=True, padx=5)
btn_stop = ctk.CTkButton(btn_frame, text="⏹ STOP BOT", command=stop_bot, font=("Helvetica", 14, "bold"), fg_color="gray", state="disabled", height=40)
btn_stop.pack(side="right", fill="x", expand=True, padx=5)

ctk.CTkLabel(right_panel, text="📜 Activity Log", font=("Helvetica", 14, "bold")).pack(pady=(10,0))
log_box = ctk.CTkTextbox(right_panel, width=320, height=500, state="disabled", font=("Consolas", 12))
log_box.pack(padx=10, pady=10, fill="both", expand=True)

refresh_all_devices()
threading.Thread(target=video_preview_worker, daemon=True).start()
root.mainloop()