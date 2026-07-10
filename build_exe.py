import sys
import subprocess

def build_bot():
    print("🔄 ขั้นตอนที่ 1: กำลังบังคับติดตั้ง PyInstaller ให้ถูกที่...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    print("\n📦 ขั้นตอนที่ 2: กำลังแพ็กไฟล์ botADB.py เป็น .exe ไฟล์เดียวจบ (อาจจะใช้เวลาสักครู่)...")
    
    # 🎯 ใช้คำสั่ง --onefile และยัดรูป *.png ทั้งหมดฝังเข้าไปในไฟล์ .exe 
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller", 
        "--onefile", 
        "--noconsole", 
        "--add-data", "*.png;.", 
        "botADB.py"
    ])
    
    print("\n✅ เสร็จสมบูรณ์แบบ 100%! ไปดูในโฟลเดอร์ dist ได้เลยครับ")

if __name__ == "__main__":
    build_bot()