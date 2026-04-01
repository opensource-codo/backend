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
            print("[INFO] 클립보드가 비어 있어 Ctrl+C 실행")
        else:
            pyautogui.hotkey('ctrl', 'v')
            print(f"[INFO] 클립보드에 내용이 있어 Ctrl+V 실행\n내용: {copied_text}")
            pyperclip.copy("")

with mouse.Listener(on_click=on_click) as listener:
    listener.join()
