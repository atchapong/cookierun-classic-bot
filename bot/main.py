import win32gui, cv2, time, threading, random, win32con, winsound
import numpy as np
import customtkinter as ctk 
from PIL import Image
from vision import VisionBot
from controller import ControllerBot

# --- Setup Classes (สำหรับพรีวิวภาพและสแกนจอ) ---
vision = VisionBot()
ctrl = ControllerBot()

# --- Global Configs ---
bot_running = False
program_closing = False
target_window_name = "" 
jump_mode = "Auto Jump"
current_jump_key = 0x26
active_bots = [] # เก็บรายชื่อบอทแต่ละจอ

# พจนานุกรมแปลงชื่อปุ่มเป็นรหัสคีย์บอร์ด Windows (Virtual Key Codes)
KEY_MAP = {
    "Up Arrow": 0x26,
    "Spacebar": 0x20,
    "W": 0x57,
    "Enter": 0x0D
}

# ==========================================
# พจนานุกรมแปลงชื่อบูสเตอร์ -> ไฟล์รูปภาพ
# ==========================================
BOOST_MAP = {
    "❌ ไม่ซื้อ Boost": "none",
    "💰 เหรียญ 2 เท่า (Double Coins)": "boost_double_coin.png",
    "🛡️ เลือดลดช้า 15% (-15% HP drain)": "boost_hp_drain.png",
    "✨ พลังงานจากโพชั่น 20%": "boost_potion.png",
    "💥 โอกาสชนสิ่งกีดขวาง 70%": "boost_crush.png",
    "🧲 พลังแม่เหล็ก (Magnetic)": "boost_magnet.png"
}

# --- UI Setup ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
root = ctk.CTk()
root.title("Cookie Run AI Bot - V44.1 (Multi-Instance / Fix Layout & Friend Bug)")
root.geometry("920x620")
root.resizable(False, False)

show_preview_var = ctk.BooleanVar(value=False)
enable_item_page_var = ctk.BooleanVar(value=True)
use_boost_var = ctk.BooleanVar(value=False) # 🌟 เอากลับมาแล้วสำหรับแบบ B
target_boost_var = ctk.StringVar(value="❌ ไม่ซื้อ Boost")    
use_relay_var = ctk.BooleanVar(value=False) # 🌟 เพิ่มสวิตช์คุกกี้ตัวผลัด    
min_delay_var = ctk.StringVar(value="8.0")
max_delay_var = ctk.StringVar(value="10.0")
gacha_mode_var = ctk.StringVar(value="สุ่มแบบ Multi") # 🌟 ตัวแปรเก็บโหมดการสุ่ม

def log_msg(msg):
    timestamp = time.strftime("[%H:%M:%S] ")
    log_box.configure(state="normal")
    log_box.insert("end", timestamp + msg + "\n")
    log_box.see("end")
    log_box.configure(state="disabled")

def on_window_select(choice):
    global target_window_name
    target_window_name = choice
    log_msg(f"📺 เปลี่ยนหน้าจอพรีวิวเป็น: {choice}")

def refresh_all_devices():
    global target_window_name
    win_list = ctrl.get_emulator_windows()
    window_combo.configure(values=win_list if win_list else [""])
    if win_list:
        window_combo.set(win_list[0])
        target_window_name = window_combo.get().strip()
    else:
        window_combo.set('')
        target_window_name = ""
        
    if ctrl.scan_devices():
        adb_status_badge.configure(text="✅ เชื่อมต่อแล้ว", fg_color="#2ecc71")
        log_msg(f"🔄 สแกนพบจอเกมทั้งหมด {len(win_list)} จอ")
        return
    adb_status_badge.configure(text="❌ ไม่พบอุปกรณ์", fg_color="#e74c3c")

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
        child_windows = ctrl.get_child_windows(main_hwnd)
        if not child_windows: continue
        frame, _, _ = vision.capture_screen(child_windows[-1])
        if frame is None: continue
        cv2_resized = cv2.resize(frame, (480, 270))  
        cv2_rgb = cv2.cvtColor(cv2_resized, cv2.COLOR_BGR2RGB)
        img_tk = ctk.CTkImage(light_image=Image.fromarray(cv2_rgb), dark_image=Image.fromarray(cv2_rgb), size=(480, 270))
        video_label.configure(image=img_tk, text="")

# =========================================================================
# 🧠 BRAIN: MULTI-THREADING BOT WORKER
# =========================================================================
class BotWorker(threading.Thread):
    def __init__(self, window_name, device_index):
        super().__init__()
        self.window_name = window_name
        self.device_index = device_index
        self.running = True
        self.vision = VisionBot()
        self.ctrl = ControllerBot()
        self.d_name = self.window_name.replace("LDPlayer", "LD").strip()

    def run(self):
        global bot_running, jump_mode, current_jump_key
        
        if not self.ctrl.scan_devices() or not self.ctrl.connect_device(self.device_index):
            log_msg(f"❌ [{self.d_name}] ระบบเชื่อมต่อ ADB ล้มเหลว!")
            return

        main_hwnd = win32gui.FindWindow(None, self.window_name)
        if main_hwnd == 0:
            log_msg(f"❌ [{self.d_name}] ไม่พบหน้าต่างจอ")
            return

        child_windows = self.ctrl.get_child_windows(main_hwnd)
        if child_windows:
            _, screen_w, _ = self.vision.capture_screen(child_windows[-1])
            self.vision.preload_templates(screen_w)
            
        last_jump_time, next_click_allowed_time, last_scan_time = 0, 0, 0
        last_action_time = time.time()
        current_page, last_logged_page = "UNKNOWN_OR_LOADING", ""
        log_msg(f"🤖 [{self.d_name}] พร้อมทำงาน! (ปุ่มกระโดด: {key_combo.get()})")
        
        while self.running and bot_running:
            time.sleep(0.016)
            child_windows = self.ctrl.get_child_windows(main_hwnd)
            if not child_windows: continue
            target_hwnd = child_windows[-1]
            
            frame, width, height = self.vision.capture_screen(target_hwnd)
            if frame is None: continue
            
            current_time = time.time()
            scan_delay = 0.1 if current_page == "UNKNOWN_OR_LOADING" else 0.5  
            
            if current_time - last_scan_time >= scan_delay:
                last_scan_time = current_time
                current_page = self.vision.get_current_page(frame, enable_item_page_var.get())
                    
            if current_page != last_logged_page and current_page != "UNKNOWN_OR_LOADING":
                log_msg(f"🖥️ [{self.d_name}] เข้าสู่ STATE: [{current_page}]")
                last_logged_page = current_page
                if current_page in ["BOOST_POPUP", "RELAY_POPUP", "ANY_CONFIRM_POPUP", "SURPRISE_CAPTCHA", "CRYSTAL_WARNING_POPUP"]:
                    next_click_allowed_time = 0.0 
                    
            target_boost_name = target_boost_var.get()
            
            if current_page == "ITEM_PAGE" and target_boost_name != "❌ ไม่ซื้อ Boost" and next_click_allowed_time > current_time + 3.0:
                target_img = BOOST_MAP.get(target_boost_name, "none")
                if target_img != "none" and self.vision.find_template(frame, target_img, [0.4, 0.9, 0.2, 0.8], 0.75):
                    log_msg(f"⚡ [{self.d_name}] สุ่มได้ {target_boost_name} แล้ว! ลุยต่อทันที!")
                    next_click_allowed_time = 0.0
            
            if current_page == "SURPRISE_CAPTCHA":
                log_msg(f"🔍 [{self.d_name}] กำลังวิเคราะห์สกรีนดักบอท...")
                time.sleep(1.0) 
                fresh_frame, w, h = self.vision.capture_screen(target_hwnd)
                target_pt = self.vision.solve_captcha(fresh_frame)
                if target_pt:
                    self.ctrl.click(target_pt[0], target_pt[1], w, h)
                    log_msg(f"🎯 [{self.d_name}] แก้สกรีนสำเร็จ!")
                else:
                    log_msg(f"⚠️ [{self.d_name}] ระบบวิเคราะห์พลาด รอแก้ด้วยมือ...")
                    winsound.Beep(2000, 300)
                last_action_time, next_click_allowed_time = time.time(), time.time() + 2.0
                continue

           # 🌟 เมื่อจับได้ว่าอยู่หน้าเพื่อน ให้สั่งกด Back (Keyevent 4)
            elif current_page == "FRIEND_INFO_POPUP":
                log_msg(f"⚠️ [{self.d_name}] เผลอเปิดหน้าเพื่อน! สั่งปุ่ม Back ย้อนกลับ...")
                
                # 🎯 แก้บั๊กโค้ดพัง: เรียกใช้ adb_device.shell เพื่อสั่งกดปุ่ม Back ตรงๆ
                if self.ctrl.adb_device:
                    self.ctrl.adb_device.shell("input keyevent 4")
                
                # หน่วงเวลา 1.5 วินาที ให้หน้าต่างเพื่อนมันปิดลงจนสนิท ก่อนรันรอบต่อไป
                last_action_time, next_click_allowed_time = current_time, current_time + 1.5
                continue
                
            elif current_page == "CRYSTAL_WARNING_POPUP":
                log_msg(f"⚠️ [{self.d_name}] เงินหมด! เปลี่ยนเป็นโหมด 'ไม่ซื้อ Boost' อัตโนมัติ!")
                target_boost_var.set("❌ ไม่ซื้อ Boost") # 🌟 สั่งเซ็ตดรอปดาวน์เป็นไม่ซื้อ
                cancel_match = self.vision.find_template(frame, "btn_cancel.png", [0.4, 0.9, 0.2, 0.8], 0.70)
                if cancel_match: self.ctrl.click(cancel_match[0], cancel_match[1], width, height)
                else: self.ctrl.click(int(width * 0.42), int(height * 0.62), width, height)
                last_action_time, next_click_allowed_time = current_time, current_time + 2.0
                continue

            elif current_page == "BOOST_POPUP":
                # 🌟 ทำหน้าที่จัดการ "ป๊อปอัปบูสเตอร์สีฟ้า" ตอนเริ่มด่านเท่านั้น!
                if use_boost_var.get():
                    log_msg(f"🚀 [{self.d_name}] กดใช้บูสเตอร์ด่าน (สีฟ้า)!")
                    # ค้นหาปุ่มกดใช้/ซื้อ หรือ จิ้มตรงกลางป๊อปอัป
                    match_loc = self.vision.find_template(frame, "btn_buy_boost.png", [0.2, 0.8, 0.4, 0.8], 0.60)
                    if match_loc: 
                        self.ctrl.click(match_loc[0], match_loc[1], width, height)
                    else: 
                        self.ctrl.click(int(width * 0.50), int(height * 0.50), width, height)
                else:
                    log_msg(f"❌ [{self.d_name}] ปิดสวิตช์บูสเตอร์ด่านอยู่ กดปุ่ม X ข้าม...")
                    # จิ้มมุมขวาบนของป๊อปอัป (ปุ่มกากบาท X)
                    self.ctrl.click(int(width * 0.78), int(height * 0.25), width, height)
                
                last_action_time, next_click_allowed_time = current_time, current_time + 1.0 
                continue

            elif current_page == "RELAY_POPUP":
                if use_relay_var.get():
                    match_loc = self.vision.find_template(frame, "item_relay.png", [0.0, 1.0, 0.0, 1.0], 0.60)
                    if match_loc: self.ctrl.click(match_loc[0], match_loc[1], width, height)
                    else: self.ctrl.click(int(width * 0.50), int(height * 0.50), width, height)
                else: self.ctrl.click(int(width * 0.78), int(height * 0.25), width, height)
                last_action_time, next_click_allowed_time = current_time, current_time + 0.1 
                continue

            if current_page == "PLAYING_GAME":
                last_action_time = current_time 
                if jump_mode == "Auto Jump":
                    if current_time - last_jump_time > random.uniform(0.55, 0.85):
                        self.ctrl.jump(child_windows, current_jump_key) 
                        last_jump_time = current_time
                elif jump_mode == "Jelly Hunter":
                    roi = frame[int(height * 0.40):int(height * 0.65), int(width * 0.38):int(width * 0.48)]
                    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                    mask_y = cv2.inRange(hsv, np.array([15, 100, 100]), np.array([35, 255, 255]))
                    mask_p = cv2.inRange(hsv, np.array([140, 50, 50]), np.array([170, 255, 255]))
                    if np.sum(cv2.bitwise_or(mask_y, mask_p) > 0) > 80:
                        if current_time - last_jump_time > random.uniform(0.65, 0.85):
                            self.ctrl.jump(child_windows, current_jump_key) 
                            last_jump_time = current_time
                continue
                
            if current_time >= next_click_allowed_time:
                try: min_d, max_d = float(min_delay_var.get()), float(max_delay_var.get())
                except: min_d, max_d = 8.0, 10.0
                random_wait = random.uniform(min_d, max_d)
                
                # 🌟 BUGFIX: ย้ายพิกัด Anti-Stuck ไปมุมซ้ายบนของจอ (0.50, 0.08) ไม่ให้จิ้มโดนโปรไฟล์เพื่อน!
                if current_time - last_action_time >= 15.0 and current_page != "UNKNOWN_OR_LOADING":
                    log_msg(f"⚔️ [{self.d_name}] [Anti-Stuck] สะกิดจอด้านบน ป้องกันค้าง ({current_page})")
                    self.ctrl.click(int(width * 0.50), int(height * 0.08), width, height)
                    last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                    continue

                if current_page == "LOBBY_PAGE":
                    match = self.vision.find_template(frame, "btn_play.png", [0.70, 0.95, 0.60, 0.95], 0.65)
                    if match: self.ctrl.click(match[0], match[1], width, height)
                    last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                        
                elif current_page == "ITEM_PAGE":
                    target_boost_name = target_boost_var.get()
                    
                    # 🌟 1. ถ้าเลือกบัฟเอาไว้ ให้ลุยสุ่มกาชา
                    if target_boost_name != "❌ ไม่ซื้อ Boost":
                        target_img = BOOST_MAP.get(target_boost_name, "none")
                        
                        # 1.1 เจอรูปบัฟที่ต้องการแล้ว -> กด Play
                        if target_img != "none" and self.vision.find_template(frame, target_img, [0.4, 0.9, 0.2, 0.8], 0.75):
                            match = self.vision.find_template(frame, "btn_play.png", [0.70, 0.95, 0.60, 0.95], 0.65)
                            if match: self.ctrl.click(match[0], match[1], width, height)
                            else: self.ctrl.click(int(width * 0.82), int(height * 0.85), width, height)
                            last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                            
                        # 1.2 ยังไม่เจอรูปบัฟ -> ต้องสุ่มใหม่ หรือ กำลังสุ่มอยู่
                        else:
                            # 🎯 เช็กโหมดสุ่มว่าเถ้าแก่เลือกแบบไหนไว้
                            if gacha_mode_var.get() == "สุ่มแบบ Multi":
                                multi = self.vision.find_template(frame, "btn_multi.png", [0.3, 0.9, 0.5, 1.0], 0.70)
                                if multi: 
                                    self.ctrl.click(multi[0], multi[1], width, height)
                                    # 🌟 ปรับเป็น 20 วิ ตามที่เถ้าแก่สั่ง!
                                    last_action_time, next_click_allowed_time = current_time, current_time + 20.0
                                else:
                                    red = self.vision.find_template(frame, "red_box.png", [0.3, 0.9, 0.2, 0.8], 0.70)
                                    if red: 
                                        self.ctrl.click(red[0], red[1], width, height)
                                        last_action_time, next_click_allowed_time = current_time, current_time + 2.0
                                    else:
                                        next_click_allowed_time = current_time + 0.5 
                                        
                            else:
                                # ☝️ โหมดสุ่มทีละอัน (Single-buy)
                                confirm_buy = self.vision.find_template(frame, "btn_buy_confirm.png", [0.4, 0.9, 0.4, 0.85], 0.70)
                                if confirm_buy:
                                    log_msg(f"✅ [{self.d_name}] กดยืนยันสุ่มกาชาทับของเดิม!")
                                    self.ctrl.click(confirm_buy[0], confirm_buy[1], width, height)
                                    last_action_time, next_click_allowed_time = current_time, current_time + 1.5
                                else:
                                    single_buy = self.vision.find_template(frame, "btn_buy_single.png", [0.2, 0.8, 0.4, 0.9], 0.70)
                                    if single_buy: 
                                        self.ctrl.click(single_buy[0], single_buy[1], width, height)
                                        last_action_time, next_click_allowed_time = current_time, current_time + 1.5
                                    else: 
                                        # 🎯 แก้บั๊ก: เพิ่มการสแกนหา "กล่องแดง" ก่อน!
                                        red = self.vision.find_template(frame, "red_box.png", [0.3, 0.9, 0.2, 0.8], 0.70)
                                        if red: 
                                            self.ctrl.click(red[0], red[1], width, height)
                                            last_action_time, next_click_allowed_time = current_time, current_time + 2.0
                                        else:
                                            self.ctrl.click(int(width * 0.50), int(height * 0.70), width, height)
                                            last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                    
                    # 🌟 2. ถ้าเลือก "ไม่ซื้อ" ให้กดข้ามไปปุ่ม Play ทันที
                    else:
                        match = self.vision.find_template(frame, "btn_play.png", [0.70, 0.95, 0.60, 0.95], 0.65)
                        if match: self.ctrl.click(match[0], match[1], width, height)
                        else: self.ctrl.click(int(width * 0.82), int(height * 0.85), width, height)
                        last_action_time, next_click_allowed_time = current_time, current_time + random_wait

                # ==========================================
                # 🌟 เอาโค้ดที่หายไปกลับคืนมา วางต่อจาก ITEM_PAGE เลยครับ!
                # ==========================================
                elif current_page == "MULTI_BUY_PAGE":
                    match = self.vision.find_template(frame, "btn_multi_buy.png", [0.6, 1.0, 0.2, 0.8], 0.75)
                    if match:
                        log_msg(f"🎰 [{self.d_name}] กดปุ่มยืนยัน Multi-Buy!")
                        self.ctrl.click(match[0], match[1], width, height)
                        # 🌟 ปรับเวลาจาก 90 วิ เหลือแค่ 2 วิ บอทจะได้กดรัวๆ!
                        next_click_allowed_time = current_time + 2.0 
                    else: 
                        self.ctrl.click(int(width * 0.50), int(height * 0.80), width, height)
                        next_click_allowed_time = current_time + random_wait
                    last_action_time = current_time

                elif current_page in ["MYSTERY_BOX_MAIN_PAGE", "MYSTERY_BOX_CONFIRM_PAGE"]:
                    match = self.vision.find_template(frame, "btn_open_all.png", [0.70, 0.95, 0.35, 0.65], 0.75) or \
                            self.vision.find_template(frame, "btn_mystery_box_confirm.png", [0.75, 0.95, 0.40, 0.60], 0.75)
                    if match: self.ctrl.click(match[0], match[1], width, height)
                    last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                        
                elif current_page == "ANY_CONFIRM_POPUP":
                    match = self.vision.find_template(frame, "btn_confirm.png", [0.40, 0.95, 0.20, 0.80], 0.70)
                    if match: 
                        self.ctrl.click(match[0], match[1], width, height)
                    else: 
                        self.ctrl.click(int(width * 0.50), int(height * 0.75), width, height)
                    last_action_time, next_click_allowed_time = current_time, current_time + random_wait
                        
                elif current_page == "RESULT_PAGE":
                    match = self.vision.find_template(frame, "btn_ok.png", [0.70, 0.95, 0.20, 0.50], 0.75)
                    if match: 
                        time.sleep(random.uniform(6.0, 7.5))
                        self.ctrl.click(match[0], match[1], width, height)
                    last_action_time, next_click_allowed_time = time.time(), time.time() + random_wait

# =========================================================================
# UI Controllers 
# =========================================================================
def start_bot():
    global bot_running, jump_mode, current_jump_key
    
    win_list = window_combo.cget("values")
    if not win_list or win_list[0] == "":
        log_msg("❌ ไม่พบจอ กรุณากดปุ่มสแกนจอก่อนครับ!")
        return
        
    selected_key = key_combo.get()
    current_jump_key = KEY_MAP.get(selected_key, 0x26)
    
    bot_running = True
    jump_mode = mode_combo.get()
    status_label.configure(text=f"🟢 WORKING ({len(win_list)} จอ)", text_color="#2ecc71")
    btn_start.configure(state="disabled", fg_color="gray")
    btn_stop.configure(state="normal", fg_color="#e74c3c")
    
    active_bots.clear()
    for idx, w_name in enumerate(win_list):
        bot = BotWorker(window_name=w_name, device_index=idx)
        bot.start()
        active_bots.append(bot)
        time.sleep(0.5)

def stop_bot():
    global bot_running
    bot_running = False
    for bot in active_bots:
        bot.running = False
    status_label.configure(text="🔴 STATUS: STOPPED", text_color="#e74c3c")
    btn_start.configure(state="normal", fg_color="#3498db")
    btn_stop.configure(state="disabled", fg_color="gray")
    log_msg("⏹ หยุดการทำงานทุกจอ")

def on_closing():
    global program_closing, bot_running
    program_closing, bot_running = True, False
    for bot in active_bots:
        bot.running = False
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

# -- UI Layout --
left_panel = ctk.CTkFrame(root, corner_radius=10)
left_panel.pack(side="left", fill="both", expand=True, padx=(10,5), pady=10)
right_panel = ctk.CTkFrame(root, corner_radius=10, width=300)
right_panel.pack(side="right", fill="y", padx=(5,10), pady=10)

video_label = ctk.CTkLabel(left_panel, text="📺 กำลังเชื่อมต่อภาพ...", width=480, height=270, fg_color="black", corner_radius=10)
video_label.pack(pady=10, padx=10)

control_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
control_frame.pack(fill="x", padx=10, pady=5)
ctk.CTkLabel(control_frame, text="🎯 เลือกจอ:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
window_combo = ctk.CTkComboBox(control_frame, width=180, values=[], command=on_window_select)
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

# ==========================================
# 🛠️ โซน switch_frame (แบบ B: เลย์เอาต์เป๊ะ ไม่ทับกัน)
# ==========================================
switch_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
switch_frame.pack(fill="x", padx=10, pady=5)

# Row 0: พรีวิว และ แวะหน้าไอเทม
ctk.CTkSwitch(switch_frame, text="👁️ พรีวิวภาพจอ", variable=show_preview_var).grid(row=0, column=0, padx=10, pady=5, sticky="w")
ctk.CTkSwitch(switch_frame, text="🎒 แวะหน้าไอเทม", variable=enable_item_page_var).grid(row=0, column=1, padx=10, pady=5, sticky="w")

# Row 1: สวิตช์เปิด/ปิด บูสเตอร์ด่าน และ เมนูเลือกชนิดบูสเตอร์
ctk.CTkSwitch(switch_frame, text="🚀 ใช้บูสเตอร์ด่าน", variable=use_boost_var).grid(row=1, column=0, padx=10, pady=5, sticky="w")
boost_combo = ctk.CTkComboBox(switch_frame, values=list(BOOST_MAP.keys()), variable=target_boost_var, width=160)
boost_combo.grid(row=1, column=1, padx=10, pady=5, sticky="w")

# Row 2: สวิตช์คุกกี้ตัวผลัด (ลบ Auto Gacha เดิมออกไปแล้ว)
ctk.CTkSwitch(switch_frame, text="🔄 ใช้คุกกี้ตัวผลัด", variable=use_relay_var).grid(row=2, column=0, padx=10, pady=5, sticky="w")

# 🌟 Row 3 (เพิ่มใหม่): เลือกโหมดสุ่มกาชา
ctk.CTkLabel(switch_frame, text="⚙️ โหมดสุ่มกาชา:").grid(row=3, column=0, padx=10, pady=5, sticky="w")
gacha_mode_combo = ctk.CTkComboBox(switch_frame, values=["สุ่มแบบ Multi", "สุ่มทีละอัน"], variable=gacha_mode_var, width=160)
gacha_mode_combo.grid(row=3, column=1, padx=10, pady=5, sticky="w")

status_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
status_frame.pack(fill="x", padx=10, pady=5)
status_label = ctk.CTkLabel(status_frame, text="🔴 STATUS: STOPPED", font=("Helvetica", 14, "bold"), text_color="#e74c3c")
status_label.pack(side="left", padx=10)

key_combo = ctk.CTkComboBox(status_frame, values=["Up Arrow", "Spacebar", "W", "Enter"], width=100)
key_combo.pack(side="right", padx=(5, 10))
key_combo.set("Up Arrow")

mode_combo = ctk.CTkComboBox(status_frame, values=["Jelly Hunter", "Auto Jump", "No Jump"], width=130)
mode_combo.pack(side="right", padx=5)
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