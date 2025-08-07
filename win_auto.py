#워드 파일을 pdf로 변환하는 기능
#
#사용자 상호작용 기반 단계별 가이드 구현
from pywinauto.application import Application
from pywinauto.findwindows import ElementNotFoundError
from pywinauto import timings
import time
import psutil
import pyautogui
timings.Timings.after_clickinput_wait = 0.01  # 기본 0.5 → 0.01로 줄이기
timings.Timings.after_setcursorpos_wait = 0.01

# 1. 실행 중인 워드 프로세스 PID 찾기
pid = None
signal = 0

for proc in psutil.process_iter(['name', 'pid']):
    if proc.info['name'] and 'WINWORD.EXE' in proc.info['name']:
        pid = proc.info['pid']
        print(f"Word PID: {pid}")

if pid is None:
    print("Word 프로세스가 실행 중이지 않습니다.")
    exit()

# 2. 워드 애플리케이션에 UIA 백엔드로 연결
app = Application(backend="uia").connect(process=pid)

# 3. 워드 메인 윈도우 객체 가져오기
win = app.window(title_re=".*Word.*")
win.wait('exists enabled visible ready', timeout=15)


# 4. '파일 탭' 컨트롤 찾기 및 하이라이트
button_file = win.child_window(title="파일 탭", control_type="Button")
button_file.draw_outline(thickness=4)
time.sleep(2)
button_file.click()
signal+=1

print("1단계: '파일 탭' 선택됨.")

if signal ==1:
    button_export = win.child_window(title="내보내기", control_type="ListItem")
    button_export.draw_outline(thickness=4)
    time.sleep(2)
    #button_export.is_visible()
    button_export.click_input()
    print("2단계: '내보내기' 선택됨.")
    signal +=1
# 6. 'PDF/XPS 문서 만들기' 탭 찾기 및 하이라이트
#button_pdf_tab = pane_ribbon.child_window(title="PDF/XPS 문서 만들기", control_type="TabItem")

if signal == 2:
    button_pdf_tab = win.child_window(title="PDF/XPS 문서 만들기", control_type="TabItem")
    button_pdf_tab.draw_outline(thickness=4)
    time.sleep(2)
    button_pdf_tab.click_input()
    signal +=1
    print("3단계: 'PDF/XPS 문서 만들기' 선택됨.")
   


# 7. 'PDF/XPS 만들기' 버튼 찾기 및 하이라이트
#button_pdf_create = pane_ribbon.child_window(title="PDF/XPS 만들기", control_type="Button")
if signal == 3:
    button_pdf_create = win.child_window(title="PDF/XPS 만들기", control_type="Button")
    button_pdf_create.draw_outline(thickness=4)
    time.sleep(2)
    button_pdf_create.click_input()
    signal +=1
    print("4단계: 'PDF/XPS 만들기' 선택됨.")
