from pywinauto import Application
import subprocess
import time

# explorer.exe를 통해 ms-settings: URI로 설정 앱 실행
subprocess.Popen(['explorer.exe', 'ms-settings:'])
time.sleep(2)  # 설정 앱이 뜰 시간을 줍니다.

# 설정 앱 창에 연결
app = Application(backend="uia").connect(title_re="설정|Settings")
settings_dlg = app.window(title_re="설정|Settings")
settings_dlg.wait('visible')

# 3. 왼쪽 메뉴에서 'Windows 업데이트' 클릭 (한글/영어 지원)
try:
    update_menu = settings_dlg.child_window(title='Windows 업데이트', control_type="ListItem")
    update_menu.click_input()
except:
    update_menu = settings_dlg.child_window(title='Windows Update', control_type="ListItem")
    update_menu.click_input()

time.sleep(2)  # 페이지 전환 대기

# 4. '업데이트 확인' 버튼 클릭
try:
    check_button = settings_dlg.child_window(title='업데이트 확인', control_type="Button")
    check_button.click_input()
except:
    check_button = settings_dlg.child_window(title='Check for updates', control_type="Button")
    check_button.click_input()

print("업데이트 확인 버튼 클릭!")

# 5. 만약 '다운로드' 또는 '지금 설치' 버튼이 있으면 자동 클릭 (옵션)
for btn_title in ['다운로드', '지금 설치', 'Download', 'Install now']:
    try:
        install_button = settings_dlg.child_window(title=btn_title, control_type="Button")
        install_button.click_input()
        print(f"'{btn_title}' 버튼 클릭!")
        break
    except Exception:
        continue

# 종료
settings_dlg.close()
