import win32gui, win32ui, win32con, cv2, numpy as np, os, sys, ctypes

try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except: pass

class VisionBot:
    def __init__(self):
        self.TEMPLATE_BASE_WIDTH = 1600.0  
        self.cached_templates = {}

    def resource_path(self, relative_path):
        try: 
            # กรณีรันผ่านไฟล์ .exe (PyInstaller)
            base_path = sys._MEIPASS
            return os.path.join(base_path, "image", relative_path)
        except Exception: 
            # 🎯 BUGFIX: กรณีรันไฟล์ .py 
            # ให้ถอยหลัง 1 โฟลเดอร์ (ออกจาก bot) แล้วพุ่งเข้าโฟลเดอร์ image
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            return os.path.join(base_path, "image", relative_path)

    def capture_screen(self, hwnd):
        try:
            left, top, right, bottom = win32gui.GetClientRect(hwnd)
            w, h = right - left, bottom - top
            if w <= 0 or h <= 0: return None, 1280, 720
            
            wDC = win32gui.GetWindowDC(hwnd)
            dcObj = win32ui.CreateDCFromHandle(wDC)
            cDC = dcObj.CreateCompatibleDC()
            dataBitMap = win32ui.CreateBitmap()
            dataBitMap.CreateCompatibleBitmap(dcObj, w, h)
            cDC.SelectObject(dataBitMap)
            
            result = ctypes.windll.user32.PrintWindow(hwnd, cDC.GetSafeHdc(), 3)
            if result != 1: cDC.BitBlt((0, 0), (w, h), dcObj, (0, 0), win32con.SRCCOPY)
                
            signedIntsArray = dataBitMap.GetBitmapBits(True)
            img = np.frombuffer(signedIntsArray, dtype='uint8')
            img.shape = (h, w, 4)
            
            win32gui.DeleteObject(dataBitMap.GetHandle())
            cDC.DeleteDC()
            dcObj.DeleteDC()
            win32gui.ReleaseDC(hwnd, wDC)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR), w, h
        except: return None, 1280, 720

    def preload_templates(self, current_screen_width, logger=None):
        scale = current_screen_width / self.TEMPLATE_BASE_WIDTH
        if logger: logger(f"🔄 โหลด AI Vision (Scale: {scale:.2f})...")
        self.cached_templates.clear() 
        missing_count = 0
        
        # 🌟 1. ดึง Path ของโฟลเดอร์ image (โดยส่งค่า string ว่างเข้าไป)
        image_dir = self.resource_path("") 
        
        # เช็กก่อนว่ามีโฟลเดอร์นี้อยู่จริงไหม
        if not os.path.exists(image_dir):
            if logger: logger(f"❌ ไม่พบโฟลเดอร์รูปภาพที่: {image_dir}")
            return

        # 🌟 2. [DYNAMIC] สแกนหาไฟล์ .png ทั้งหมดในโฟลเดอร์มาใส่ List อัตโนมัติ!
        image_list = [f for f in os.listdir(image_dir) if f.lower().endswith('.png')]
        
        if logger: logger(f"📂 สแกนพบรูปภาพในคลังทั้งหมด {len(image_list)} ไฟล์")

        for img_name in image_list:
            path = os.path.join(image_dir, img_name) 
            
            if os.path.exists(path):
                img_array = np.fromfile(path, np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                
                if img is not None:
                    # ปรับขนาดภาพตามจอ แล้วยัดลง Dictionary
                    new_w, new_h = int(img.shape[1] * scale), int(img.shape[0] * scale)
                    self.cached_templates[img_name] = cv2.resize(img, (new_w, new_h))
                else:
                    missing_count += 1
                    if logger: logger(f"❌ รูปภาพเสียหาย/อ่านไม่ได้: {img_name}")
            else:
                missing_count += 1
                if logger: logger(f"❌ ไม่พบรูปภาพ: {path}")
                
        if missing_count > 0 and logger:
            logger(f"⚠️ บอทอาจเอ๋อ! ขาดไฟล์รูปทั้งหมด {missing_count} รูป")

    def find_template(self, main_frame, template_name, crop_limits, threshold=0.70):
        if template_name not in self.cached_templates: return None
        template = self.cached_templates[template_name]
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

    def find_green_btn(self, main_frame, crop_limits):
        h_max, w_max = main_frame.shape[:2]
        y1, y2 = int(h_max * crop_limits[0]), int(h_max * crop_limits[1])
        x1, x2 = int(w_max * crop_limits[2]), int(w_max * crop_limits[3])
        zone_frame = main_frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(zone_frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([35, 120, 120]), np.array([85, 255, 255]))
        if cv2.countNonZero(mask) > (zone_frame.shape[0] * zone_frame.shape[1] * 0.05):
            M = cv2.moments(mask)
            if M["m00"] != 0: return (x1 + int(M["m10"] / M["m00"]), y1 + int(M["m01"] / M["m00"]))
        return None

    def solve_captcha(self, frame):
        try:
            h, w = frame.shape[:2]
            
            # 1. ล็อกเป้าหมายแบบตายตัว: ตัดภาพหน้าจอเป็น 3 ส่วน (ซ้าย, กลาง, ขวา)
            # เราใช้เปอร์เซ็นต์ (0.0 - 1.0) เพื่อให้รองรับทุกขนาดหน้าจอ
            roi_left   = frame[int(h*0.35):int(h*0.65), int(w*0.15):int(w*0.35)]
            roi_center = frame[int(h*0.35):int(h*0.65), int(w*0.40):int(w*0.60)]
            roi_right  = frame[int(h*0.35):int(h*0.65), int(w*0.65):int(w*0.85)]

            # 2. ฟังก์ชันย่อยสำหรับดึงค่าสถิติสี (Histogram) ของภาพ
            def get_hist(roi_img):
                hist = cv2.calcHist([roi_img], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
                cv2.normalize(hist, hist)
                return hist

            hist_l = get_hist(roi_left)
            hist_c = get_hist(roi_center)
            hist_r = get_hist(roi_right)

            # 3. เทียบความเหมือนของสี (Correlation: ยิ่งเข้าใกล้ 1.0 คือยิ่งเหมือนกันเป๊ะ)
            sim_lc = cv2.compareHist(hist_l, hist_c, cv2.HISTCMP_CORREL) # ซ้าย เทียบ กลาง
            sim_lr = cv2.compareHist(hist_l, hist_r, cv2.HISTCMP_CORREL) # ซ้าย เทียบ ขวา
            sim_cr = cv2.compareHist(hist_c, hist_r, cv2.HISTCMP_CORREL) # กลาง เทียบ ขวา

            # 4. ลอจิกหาใบที่แปลกแยกที่สุด (The Odd One Out)
            if sim_lc > sim_lr and sim_lc > sim_cr: 
                # ถ้า "ซ้าย" กับ "กลาง" คล้ายกันมากที่สุด -> แปลว่า "ขวา" คือตัวปลอม!
                return (int(w * 0.75), int(h * 0.50))
                
            elif sim_lr > sim_lc and sim_lr > sim_cr: 
                # ถ้า "ซ้าย" กับ "ขวา" คล้ายกันมากที่สุด -> แปลว่า "กลาง" คือตัวปลอม!
                return (int(w * 0.50), int(h * 0.50))
                
            else: 
                # ถ้า "กลาง" กับ "ขวา" คล้ายกันมากที่สุด -> แปลว่า "ซ้าย" คือตัวปลอม!
                return (int(w * 0.25), int(h * 0.50))
                
        except Exception as e:
            print(f"Error in solve_captcha: {e}")
            return None

    def get_current_page(self, frame, enable_item_page):
        if self.find_template(frame, "btn_multi_buy.png", [0.6, 1.0, 0.2, 0.8], 0.75): return "MULTI_BUY_PAGE"
         # 🌟 เพิ่มบรรทัดนี้: หาปุ่มกากบาทปิด (X) หรือข้อความบนหัวหน้าต่างเพื่อน
        if self.find_template(frame, "btn_close_friend.png", [0.0, 0.25, 0.70, 1.0], 0.70): return "FRIEND_INFO_POPUP"
        if self.find_template(frame, "id_surprise.png", [0.0, 0.20, 0.2, 0.8], 0.70): return "SURPRISE_CAPTCHA"
        if self.find_template(frame, "crystal_warning.png", [0.2, 0.8, 0.2, 0.8], 0.75): return "CRYSTAL_WARNING_POPUP"
        if self.find_template(frame, "item_boost.png", [0.0, 1.0, 0.0, 1.0], 0.60): return "BOOST_POPUP"
        if self.find_template(frame, "item_relay.png", [0.0, 1.0, 0.0, 1.0], 0.60): return "RELAY_POPUP"
        if self.find_template(frame, "btn_open_all.png", [0.70, 0.95, 0.35, 0.65], 0.75): return "MYSTERY_BOX_MAIN_PAGE"
        if self.find_template(frame, "btn_mystery_box_confirm.png", [0.75, 0.95, 0.40, 0.60], 0.75): return "MYSTERY_BOX_CONFIRM_PAGE"
        if self.find_template(frame, "id_result.png", [0.0, 0.25, 0.3, 0.7], 0.70): return "RESULT_PAGE"
        if enable_item_page and self.find_template(frame, "id_item.png", [0.0, 0.25, 0.05, 0.5], 0.70): return "ITEM_PAGE"
        if self.find_template(frame, "id_lobby.png", [0.0, 0.4, 0.0, 1.0], 0.70): return "LOBBY_PAGE"
        if self.find_template(frame, "id_playing.png", [0.0, 0.20, 0.0, 1.0], 0.70): return "PLAYING_GAME"
        # 🌟 ลบ/คอมเมนต์ find_green_btn ทิ้งไปเลย!! ให้สแกนหาแค่รูป btn_confirm.png พอครับ
        if self.find_template(frame, "btn_confirm.png", [0.4, 0.8, 0.2, 0.8], 0.70):
            return "ANY_CONFIRM_POPUP"
            
        # (และลบ/คอมเมนต์ส่วนที่เช็ก btn_send_gift.png หรือ FRIEND_INFO_POPUP ทิ้งไปได้เลยครับ ไม่จำเป็นแล้ว!)
        return "UNKNOWN_OR_LOADING"