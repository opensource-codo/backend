import time
import pyautogui
from pynput import mouse

print("이름을 변경할 파일을 클릭해주세요.")

def on_click(x, y, button, pressed):
    if pressed and button==mouse.Button.right:
        #pyautogui.click(x, y)
        #time.sleep(0.3)  # 0.3초 대기 (0.2~0.4초 사이에서 시험해보세요)
        pyautogui.press('f2')
        print("F2 실행 → 이름 변경 모드 진입 완료")

        return False  # 한 번 실행 후 종료

with mouse.Listener(on_click=on_click) as listener:
    listener.join()

