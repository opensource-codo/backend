from pywinauto import Desktop
import time
# 볼륨 슬라이더가 가질 수 있는 여러 가능한 클래스 이름들을 리스트로 정의
VOLUME_CLASSES = ["CoreWindow", "Popup", "Window", "ToolWindow", "ApplicationFrameWindow"]

desktop = Desktop(backend="uia")  # UIA 백엔드를 사용하는 Desktop 객체 생성

# 작업 표시줄 창을 찾으려고 시도함
try:
    # 작업 표시줄은 보통 "작업 표시줄"이라는 제목을 갖고 control_type은 Pane 타입임
    tray = desktop.window(title_re=".*작업 표시줄", control_type="Pane")
except Exception:
    tray = None  # 만약 찾지 못하면 None으로 설정

if tray:
    # 작업 표시줄 내부의 자식 컨트롤들을 순회
    for child in tray.children():
        cname = child.friendly_class_name() or ""  # 자식 컨트롤의 친화적 클래스명 얻기
        title = child.window_text()  # 자식 컨트롤의 창 제목(텍스트) 얻기
        # 자식 컨트롤 클래스명이 VOLUME_CLASSES 리스트 중 하나라도 포함되어 있으면
        if any(vc in cname for vc in VOLUME_CLASSES):
            print(f"작업 표시줄 내부에서 찾음: {cname} - {title}")
            try:
                child.click_input()
                time.sleep(0.5)
                child.set_focus()  # 해당 컨트롤에 포커스 주기 시도
                print("볼륨 슬라이더에 포커스 부여 (작업 표시줄 내부)")
                break  # 성공하면 탐색 종료
            except Exception:
                pass  # 포커스 실패시 무시하고 계속 탐색
else:
    # 작업 표시줄창을 못 찾았을 때 전체 데스크탑 윈도우에서 탐색
    for w in desktop.windows():
        cname = w.friendly_class_name() or ""  # 윈도우 친화적 클래스명
        title = w.window_text()  # 윈도우 제목
        # 윈도우 클래스명 중 하나라도 VOLUME_CLASSES에 포함되어 있으면
        if any(vc in cname for vc in VOLUME_CLASSES):
            print(f"데스크탑 전체에서 찾음: {cname} - {title}")
            try:
                w.click_input()
                time.sleep(0.5)
                w.set_focus()  # 포커스 주기 시도
                print("볼륨 슬라이더에 포커스 부여 (전체 윈도우 탐색)")
                break  # 성공 시 탐색 종료
            except Exception:
                pass  # 실패시 무시하고 계속 탐색
