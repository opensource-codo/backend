import screen_brightness_control as sbc

# 현재 밝기 가져오기 (모니터가 여러 대면 첫 번째 모니터 기준)
current_brightness = sbc.get_brightness(display=0)  # 또는 그냥 sbc.get_brightness()도 가능

# current_brightness는 리스트로 반환되므로 첫 값 사용 (대부분 단일 모니터 환경)
if isinstance(current_brightness, list):
    current_brightness = current_brightness[0]

print(f"현재 밝기: {current_brightness}%")

if current_brightness != 0:
    # 밝기를 10% 증가시키기 (최대 100% 초과하지 않도록)
    new_brightness = max(current_brightness - 20, 0)

    # 밝기 설정
    sbc.set_brightness(new_brightness, display=0)

    print(f"새 밝기: {new_brightness}%")
else:
    print("이미 최소 밝기 상태입니다.")
