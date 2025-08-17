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


def toggle_bluetooth(on=True):
    try:
        current_flag = bluetooth_toggle.get_toggle_state()
        if current_flag == on:
            print("이미 원하는 상태입니다. 아무 것도 실행하지 않음.")
            return
        bluetooth_toggle.click_input()
        time.sleep(2) 
        settings_dlg.close()
    except Exception as e:
        print(f"오류 발생: {e}")
    finally:
        try:
            app.kill()
        except:
            pass

# 블루투스 켜기 
toggle_bluetooth(on=False)

time.sleep(1)
pyautogui.hotkey('win', 'a')