from pywinauto import Application
import pyautogui
import subprocess
import time


# explorer.exe를 통해 ms-settings: URI로 설정 앱 실행
subprocess.Popen(['explorer.exe', 'ms-settings:'])
time.sleep(2)  # 설정 앱이 뜰 시간을 줍니다.

# 설정 앱 창에 연결
app = Application(backend="uia").connect(title_re="설정|Settings")
settings_dlg = app.window(title_re="설정|Settings")
settings_dlg.wait('visible')
try:
    settings_dlg.child_window(title="Bluetooth 및 장치", control_type="ListItem").click_input()
except Exception:
    settings_dlg.child_window(title="Bluetooth & devices", control_type="ListItem").click_input()

time.sleep(1)

# 'Bluetooth' 토글 버튼 찾기 (CheckBox 또는 RadioButton)
try:
    bluetooth_toggle = settings_dlg.child_window(title="Bluetooth", control_type="Button")
except Exception:
    bluetooth_toggle = settings_dlg.child_window(title="Bluetooth", control_type="RadioButton")
flag  = bluetooth_toggle.get_toggle_state()

def toggle_bluetooth(on=True):
    """
    Windows 설정 앱에서 블루투스 토글을 켜거나 끕니다.

    Args:
        on (bool): True이면 켜고, False이면 끕니다.
    """
    try:

        #settings_dlg.print_control_identifiers()
        # 'Bluetooth 및 장치' 페이지 클릭 (한글 / 영어 처리)

        # 토글 상태와 원하는 상태가 다르면 클릭
        if (on and bluetooth_toggle.get_toggle_state() == 0):
            bluetooth_toggle.click_input()
            print("Bluetooth ON")
            time.sleep(1)
            flag = 1
        if (not on and bluetooth_toggle.get_toggle_state() == 1):
            bluetooth_toggle.click_input()
            print("Bluetooth OFF")
            time.sleep(1)
            flag = 0

        # 설정 앱 닫기
        settings_dlg.close()
    except Exception as e:
        print(f"오류 발생: {e}")
    finally:
        try:
            app.kill()
        except:
            pass

# 블루투스 켜기 
if flag == 0:
    toggle_bluetooth(on=True)
if flag == 1:
    toggle_bluetooth(on=False)

time.sleep(1)
pyautogui.hotkey('win', 'a')