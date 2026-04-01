from pynput import mouse
import pyautogui
import pyperclip

# 클립보드 초기화
pyperclip.copy("")
print("[INFO] 프로그램 시작 - 클립보드 초기화 완료")

def on_click(x, y, button, pressed):
    if pressed and button == mouse.Button.right:  # 오른쪽 버튼 눌렸을 때만 반응
        copied_text = pyperclip.paste().strip()

        if copied_text == "":
            pyautogui.hotkey('ctrl', 'c')
            pyautogui.hotkey('ctrl', 'x')
            print("Ctrl+X 실행")
        else:
            pyautogui.hotkey('ctrl', 'x')
            print("Ctrl+X 실행")
            #pyperclip.copy("")

with mouse.Listener(on_click=on_click) as listener:
    listener.join()