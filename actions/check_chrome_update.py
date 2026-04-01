import os
import sys
import ctypes
import subprocess
import time
import psutil

# 관리자 권한 체크
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

# 실행 중인 크롬 종료
def kill_chrome():
    print("[*] 실행 중인 크롬 종료 중...")
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and 'chrome.exe' in proc.info['name'].lower():
            try:
                proc.terminate()
            except Exception as e:
                print(f"[-] 종료 실패: {e}")
    time.sleep(2)  # 종료 대기

# 크롬 실행
def run_chrome():
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(chrome_path):
        chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    if os.path.exists(chrome_path):
        subprocess.Popen([chrome_path])
        print("[+] 크롬이 재실행되었습니다.")
    else:
        print("[-] 크롬 실행 파일을 찾을 수 없습니다.")

# 크롬 업데이트 시도
def update_chrome():
    print("[*] 크롬 업데이트를 시작합니다...")

    # 1순위: winget 사용
    try:
        subprocess.run("winget upgrade --id=Google.Chrome -e --silent", check=True, shell=True)
        print("[+] winget으로 크롬 업데이트 완료")
        return True
    except subprocess.CalledProcessError:
        print("[-] winget 업데이트 실패 또는 winget 미설치")

    # 2순위: GoogleUpdate.exe 직접 호출
    google_update_path = r"C:\Program Files (x86)\Google\Update\GoogleUpdate.exe"
    if os.path.exists(google_update_path):
        try:
            subprocess.run(f'"{google_update_path}" /ua /install', check=True, shell=True)
            print("[+] GoogleUpdate.exe로 업데이트 시도 완료")
            return True
        except subprocess.CalledProcessError:
            print("[-] GoogleUpdate.exe 실행 실패")
    else:
        print("[-] GoogleUpdate.exe 경로를 찾을 수 없습니다.")

    return False

if __name__ == "__main__":
    if not is_admin():
        print("[*] 관리자 권한이 필요합니다. UAC 창을 표시합니다...")
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit()

    updated = update_chrome()

    if updated:
        kill_chrome()
        run_chrome()

    print("[*] 작업이 완료되었습니다.")
