import subprocess
from pywinauto import Desktop
import time
import sys
import ctypes # Windows API 호출 및 권한 체크에 사용

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
        # Windows API를 통해 현재 프로세스가 관리자 권한인지 검사
        # IsUserAnAdmin() 함수가 True면 관리자 권한, False면 일반 권한
    except:
        return False

if not is_admin():
    # 관리자 권한으로 스크립트 재실행
    print("[!] 관리자 권한이 필요합니다. 권한 상승 중...")
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit()


desktop = Desktop(backend="uia")
tray = desktop.window(title_re=".*작업 표시줄", control_type="Pane")

try:
    # 트레이에서 '네트워크' 또는 'Wi-Fi' 버튼 찾기 (한글/영문 OS 모두 패턴)
    wifi_icon = tray.child_window(title_re="^네트워크.*|^Wi[- ]?Fi.*|^무선.*", control_type="Button")
    wifi_icon.click_input()  # 네트워크/와이파이 아이콘 클릭 (패널 열림)
    time.sleep(0.5)  # 패널이 뜨길 잠시 대기
    print("와이파이/네트워크 설정 패널이 열렸습니다.")
except Exception as e:
    print("네트워크/와이파이 아이콘을 찾을 수 없습니다:", e)

print("현재 관리자 권한 여부:", is_admin())

# 'Wi-Fi' 어댑터를 활성화(켜기)
subprocess.run('netsh interface set interface "Wi-Fi" admin=enable', shell=True)

print("와이파이가 켜졌습니다!")