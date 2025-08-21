import screen_brightness_control as sbc

# 사용자로부터 밝기 감소값 입력 받기 (입력 없으면 10)
user_input = input("얼마나 밝기를 내리시겠습니까? (기본값 10): ")
decrease_amount = int(user_input) if user_input.strip() != '' else 10

current_brightness = sbc.get_brightness(display=0)
if isinstance(current_brightness, list):
    current_brightness = current_brightness[0]

print(f"현재 밝기: {current_brightness}%")

if current_brightness > 0:
    new_brightness = max(current_brightness - decrease_amount, 0)
    sbc.set_brightness(new_brightness, display=0)
    print(f"새 밝기: {new_brightness}%")
else:
    print("이미 최소 밝기 상태입니다.")

