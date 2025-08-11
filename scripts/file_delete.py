from pynput import mouse
import pyautogui


print("삭제할 파일을 클릭하여 주세요.")
def on_click(x, y, button, pressed):
    if pressed and button == mouse.Button.right:
        print("삭제 키 입력 실행")
        pyautogui.press('delete')
       
with mouse.Listener(on_click=on_click) as listener:
    listener.join()
