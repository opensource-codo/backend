import os
from pathlib import Path
import asyncio
from playwright.async_api import async_playwright
import shutil
import sys
import ctypes
import time
import psutil

home_dir = str(Path.home())
user_dir = os.path.join(home_dir, 'AppData', 'Local', 'Google', 'Chrome', 'User Data')

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def is_chrome_running():
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and 'chrome.exe' in proc.info['name'].lower():
            return True
    return False

def kill_chrome():
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and 'chrome.exe' in proc.info['name'].lower():
            try:
                proc.terminate()
                print(f"크롬 프로세스 종료: PID={proc.pid}")
            except Exception as e:
                print(f"크롬 프로세스 종료 실패: {e}")

async def clear_real_profile_data():
    if is_chrome_running():
        kill_chrome()
        time.sleep(3)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch_persistent_context(
            user_data_dir=user_dir,
            headless=False
        )

        page = await browser.new_page()
        await page.goto("https://www.google.com")

        await browser.clear_cookies()
        print("실제 크롬 프로필 쿠키 삭제 완료")

        cache_path = os.path.join(user_dir, "Default", "Cache")

        if os.path.exists(cache_path) and os.path.isdir(cache_path):
            shutil.rmtree(cache_path)
            print("크롬 캐시 폴더 삭제 완료")
        else:
            print("캐시 폴더가 없습니다")

        await browser.close()

if __name__ == "__main__":
    if not is_admin():
        # 관리자 권한 없이 실행 중이면 관리자 권한으로 재실행 후 종료
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()
    else:
        # 관리자 권한이 있으면 정상적으로 실행
        asyncio.run(clear_real_profile_data())
