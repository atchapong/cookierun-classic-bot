import win32gui
import win32ui
import win32con
import cv2
import numpy as np
import time
import threading
import tkinter as tk
from tkinter import ttk
import os
import winsound
from PIL import Image, ImageTk

bot_running = False
jump_mode = "Jelly Hunter"
program_closing = False

def get_inner_windows(hwnd, window_list):
    window_list.append(hwnd)
    return True

def capture_background_autosize(hwnd):
    try:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        width = right - left
        height = bottom - top
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
    except:
        return None, 1280, 720

def click_background_broadcast(windows, x, y):
    lParam = (y << 16) | x
    for sub_hwnd in windows:
        win32gui.PostMessage(sub_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
        win32gui.PostMessage(sub_hwnd, win32con.WM_LBUTTONUP, 0, lParam)

def send_key(windows, key_code):
    for sub_hwnd in windows:
        win32gui.PostMessage(sub_hwnd, win32con.WM_KEYDOWN, key_code, 0)
        win32gui.PostMessage(sub_hwnd, win32con.WM_KEYUP, key_code, 0)

def find_image_in_zone(main_frame, template_path, crop_limits, threshold=0.75):
    if not os.path.exists(template_path):
        return None
    h_max, w_max = main_frame.shape[:2]
    y1, y2 = int(h_max * crop_limits[0]), int(h_max * crop_limits[1])
    x1, x2 = int(w_max * crop_limits[2]), int(w_max * crop_limits[3])
    zone_frame = main_frame[y1:y2, x1:x2]
    template = cv2.imread(template_path)
    h, w = template.shape[:2]
    if zone_frame.shape[0] < h or zone_frame.shape[1] < w: return None
    result = cv2.matchTemplate(zone_frame, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold:
        return (x1 + max_loc[0] + int(w / 2), y1 + max_loc[1] + int(h / 2))
    return None

def check_current_page_by_image(frame):
    if find_image_in_zone(frame, "id_surprise.png", [0.0, 0.20, 0.2, 0.8], threshold=0.75):
        return "SURPRISE_CAPTCHA"
    if find_image_in_zone(frame, "id_result.png", [0.0, 0.25, 0.3, 0.7], threshold=0.75):
        return "RESULT_PAGE"
    if find_image_in_zone(frame, "id_item.png", [0.0, 0.25, 0.05, 0.5], threshold=0.75):
        return "ITEM_PAGE"
    if find_image_in_zone(frame, "btn_confirm.png", [0.55, 0.95, 0.15, 0.85], threshold=0.60):
        return "ANY_CONFIRM_POPUP"
    if find_image_in_zone(frame, "id_lobby.png", [0.0, 0.4, 0.0, 1.0], threshold=0.75):
        return "LOBBY_PAGE"
    h_max, w_max = frame.shape[:2]
    p_b, p_g, p_r = frame[int(h_max * 0.79), int(w_max * 0.45)]
    if p_g > 140 and p_g > p_r + 40 and p_g > p_b + 40: return "ANY_CONFIRM_POPUP"
    return "UNKNOWN_OR_LOADING"

def log_to_gui(message):
    timestamp = time.strftime("[%H:%M:%S] ")
    log_box.config(state="normal")
    log_box.insert(tk.END, timestamp + message + "\n")
    log_box.see(tk.END)
    log_box.config(state="disabled")

# --- 📺 Thread Preview จอสดตอนเปิดโปรแกรม ---
def video_preview_worker():
    global program_closing
    while not program_closing:
        time.sleep(0.03)  
        main_hwnd = win32gui.FindWindow(None, "LDPlayer")
        if main_hwnd == 0: continue
        child_windows = []
        win32gui.EnumChildWindows(main_hwnd, get_inner_windows, child_windows)
        if not child_windows: continue
        frame, _, _ = capture_background_autosize(child_windows[-1])
        if frame is None: continue
        cv2_resized = cv2.resize(frame, (480, 270))  
        cv2_rgb = cv2.cvtColor(cv2_resized, cv2.COLOR_BGR2RGB)
        img_tk = ImageTk.PhotoImage(image=Image.fromarray(cv2_rgb))
        video_label.img_tk = img_tk
        video_label.config(image=img_tk)

# --- 🎮 ฟังก์ชันหลักควบคุมการทำงานของบอท ---
def bot_worker():
    global bot_running, jump_mode
    main_hwnd = win32gui.FindWindow(None, "LDPlayer")
    if main_hwnd == 0:
        stop_bot()
        return
        
    child_windows = []
    win32gui.EnumChildWindows(main_hwnd, get_inner_windows, child_windows)
    
    last_jump_time = 0
    next_click_allowed_time = 0
    last_scan_time = 0  
    current_page = "UNKNOWN_OR_LOADING"
    last_logged_page = ""
    
    log_to_gui("🤖 บอทเริ่มทำงาน (ปรับเวลาสแกนตามคำสั่ง)...")
    
    while bot_running:
        time.sleep(0.016) # ลูปหลักรันที่ความเร็วปกติเพื่อการกดคีย์บอร์ดที่แม่นยำ
        child_windows = []
        win32gui.EnumChildWindows(main_hwnd, get_inner_windows, child_windows)
        if not child_windows: continue
        target_hwnd = child_windows[-1]
        
        frame, width, height = capture_background_autosize(target_hwnd)
        if frame is None: continue
        
        current_time = time.time()
        
        # ⏱️ 🆕 เงื่อนไขคูลดาวน์การสแกนจออัจฉริยะ (Dynamic Scan Delay)
        # ถ้าอยู่ในโหมดเล่นเกม ให้เว้นระยะสแกน 5.0 วินาที / ถ้าอยู่หน้าเมนูทั่วไป ให้สแกนทุก 1.0 วินาที
        scan_delay = 5.0 if current_page == "PLAYING_GAME" else 1.0
        
        if current_time - last_scan_time >= scan_delay:
            last_scan_time = current_time
            
            # เช็กปุ่ม Pause || ขวาบนก่อน
            pause_x, pause_y = int(width * 0.95), int(height * 0.06)
            pa_g = frame[pause_y, pause_x][1]
            
            if pa_g > 180:
                current_page = "PLAYING_GAME"
            else:
                # ถ้าปุ่ม Pause หายไป (แสดงว่าอยู่หน้าเมนู) ให้รันสแกนภาพหาชื่อหน้า
                current_page = check_current_page_by_image(frame)
                
        if current_page != last_logged_page and current_page != "UNKNOWN_OR_LOADING":
            log_to_gui(f"🖥️ ตรวจพบสถานะจอ: {current_page}")
            last_logged_page = current_page
            
        # 🎮 1. ฝั่งการทำแอคชั่นในด่านเกม (ทำงานต่อเนื่องทุกเฟรม ไม่โดนดีเลย์สแกนบังคับ)
        if current_page == "PLAYING_GAME":
            if jump_mode == "Auto Jump":
                if current_time - last_jump_time > 0.60:
                    send_key(child_windows, 0x26)
                    last_jump_time = current_time
            elif jump_mode == "Jelly Hunter":
                # โหมดนี้จะบังคับสแกนพื้นที่เยลลี่ทุกเฟรมเพื่อความปลอดภัย
                roi_x1, roi_x2 = int(width * 0.38), int(width * 0.48)
                roi_y1, roi_y2 = int(height * 0.40), int(height * 0.65)
                roi = frame[roi_y1:roi_y2, roi_x1:roi_x2]
                hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                mask_yellow = cv2.inRange(hsv_roi, np.array([15, 100, 100]), np.array([35, 255, 255]))
                mask_pink = cv2.inRange(hsv_roi, np.array([140, 50, 50]), np.array([170, 255, 255]))
                combined_mask = cv2.bitwise_or(mask_yellow, mask_pink)
                if np.sum(combined_mask > 0) > 80:
                    if current_time - last_jump_time > 0.7:
                        send_key(child_windows, 0x26)
                        last_jump_time = current_time
                        
        elif current_page == "SURPRISE_CAPTCHA":
            log_to_gui("🚨 เจอระบบดักบอทสุ่มการ์ด! รอคุณมาเคลียร์...")
            winsound.Beep(2000, 300)
            time.sleep(1.0)
            
        # 🏡 2. ฝั่งการกดคลิกปุ่มในหน้าเมนูต่างๆ
        elif current_time >= next_click_allowed_time:
            if current_page == "LOBBY_PAGE":
                h_max, w_max = frame.shape[:2]
                p_b, p_g, p_r = frame[int(h_max * 0.79), int(w_max * 0.45)]
                if p_g > 140 and p_g > p_r + 40 and p_g > p_b + 40:
                    log_to_gui("💥 เจอสีปุ่ม Confirm แทรกหน้า Lobby! คลิกทะลวง")
                    click_background_broadcast(child_windows, int(width * 0.50), int(height * 0.79))
                    next_click_allowed_time = current_time + 1.5
                    continue
                play_match = find_image_in_zone(frame, "btn_play.png", [0.70, 0.95, 0.60, 0.95], threshold=0.65)
                if play_match:
                    click_background_broadcast(child_windows, play_match[0], play_match[1])
                else:
                    click_background_broadcast(child_windows, int(width * 0.78), int(height * 0.86))
                log_to_gui("🏡 หน้า Lobby -> คลิกเริ่มเกม")
                next_click_allowed_time = current_time + 2.0
                    
            elif current_page == "ITEM_PAGE":
                play_match = find_image_in_zone(frame, "btn_play.png", [0.70, 0.95, 0.60, 0.95], threshold=0.65)
                if play_match:
                    click_background_broadcast(child_windows, play_match[0], play_match[1])
                else:
                    click_background_broadcast(child_windows, int(width * 0.78), int(height * 0.86))
                log_to_gui("🎒 หน้าจัดไอเทม -> คลิกเข้าด่านวิ่ง")
                next_click_allowed_time = current_time + 4.0
                    
            elif current_page == "ANY_CONFIRM_POPUP":
                confirm_match = find_image_in_zone(frame, "btn_confirm.png", [0.55, 0.95, 0.15, 0.85], threshold=0.60)
                if confirm_match:
                    click_background_broadcast(child_windows, confirm_match[0], confirm_match[1])
                else:
                    click_background_broadcast(child_windows, int(width * 0.50), int(height * 0.79))
                log_to_gui("🎁 เจอหน้าต่างป๊อปอัป -> คลิก Confirm")
                next_click_allowed_time = current_time + 1.5
                    
            elif current_page == "RESULT_PAGE":
                ok_match = find_image_in_zone(frame, "btn_ok.png", [0.70, 0.95, 0.20, 0.50], threshold=0.75)
                if ok_match:
                    click_background_broadcast(child_windows, ok_match[0], ok_match[1])
                log_to_gui("🏆 หน้าสรุปผลคะแนน -> คลิก OK")
                next_click_allowed_time = current_time + 2.5

def start_bot():
    global bot_running, jump_mode
    if not bot_running:
        bot_running = True
        jump_mode = mode_combo.get()
        status_label.config(text=f"สถานะ: กำลังทำงาน ({jump_mode})", foreground="green")
        btn_start.config(state="disabled")
        btn_stop.config(state="normal")
        log_to_gui(f"🚀 เริ่มทำงานบอทในโหมด {jump_mode}")
        threading.Thread(target=bot_worker, daemon=True).start()

def stop_bot():
    global bot_running
    bot_running = False
    status_label.config(text="สถานะ: หยุดทำงาน", foreground="red")
    btn_start.config(state="normal")
    btn_stop.config(state="disabled")
    log_to_gui("⏹ หยุดการทำงานของบอทเรียบร้อย")

def on_closing():
    global program_closing, bot_running
    program_closing = True
    bot_running = False
    root.destroy()

root = tk.Tk()
root.title("Cookie Run Dynamic-Delay Bot v15")
root.geometry("820x420")
root.resizable(False, False)
root.protocol("WM_DELETE_WINDOW", on_closing)

left_frame = ttk.Frame(root, padding=10)
left_frame.pack(side="left", fill="both", expand=True)

video_label = ttk.Label(left_frame, text="📺 กำลังเชื่อมต่อภาพกับ LDPlayer...", font=("Helvetica", 10), anchor="center", background="black", width=60)
video_label.pack(pady=5, ipadx=5, ipady=5, fill="both", expand=True)

control_frame = ttk.Frame(left_frame, padding=5)
control_frame.pack(fill="x", pady=5)

status_label = ttk.Label(control_frame, text="สถานะ: หยุดทำงาน", font=("Helvetica", 11, "bold"), foreground="red")
status_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")

ttk.Label(control_frame, text="โหมดกระโดด:").grid(row=0, column=1, padx=5, pady=5)
mode_combo = ttk.Combobox(control_frame, values=["Jelly Hunter", "Auto Jump", "No Jump"], state="readonly", width=12)
mode_combo.current(0)
mode_combo.grid(row=0, column=2, padx=5, pady=5)

btn_frame = ttk.Frame(left_frame)
btn_frame.pack(fill="x", pady=2)
btn_start = ttk.Button(btn_frame, text="▶ เริ่มทำงาน (Start)", command=start_bot)
btn_start.pack(side="left", fill="x", expand=True, padx=5)
btn_stop = ttk.Button(btn_frame, text="⏹ หยุดทำงาน (Stop)", command=stop_bot, state="disabled")
btn_stop.pack(side="right", fill="x", expand=True, padx=5)

right_frame = ttk.Frame(root, padding=10)
right_frame.pack(side="right", fill="both", expand=True)

ttk.Label(right_frame, text="📜 บันทึกกิจกรรมบอท (System Logs):", font=("Helvetica", 10, "bold")).pack(anchor="w", pady=2)
log_box = tk.Text(right_frame, width=40, height=22, state="disabled", font=("Consolas", 9), bg="#f4f4f4", fg="#333")
log_box.pack(side="left", fill="both", expand=True)

scrollbar = ttk.Scrollbar(right_frame, command=log_box.yview)
scrollbar.pack(side="right", fill="y")
log_box.config(yscrollcommand=scrollbar.set)

threading.Thread(target=video_preview_worker, daemon=True).start()

root.mainloop()