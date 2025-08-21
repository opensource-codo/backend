from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL


user_input = input("얼마나 볼륨을 내리시겠습니까? (단위: 1씩 감소, 기본값 10): ")
steps = int(user_input) if user_input.strip() != '' else 10

devices = AudioUtilities.GetSpeakers() # 시스템에서 현재 기본 스피커(오디오 출력 장치)를 가져옴
interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None) # 해당 오디오 장치의 오디오 엔드포인트 볼륨 인터페이스를 활성화
volume = cast(interface, POINTER(IAudioEndpointVolume)) # COM 인터페이스를 ctypes 포인터 타입으로 변환하여 Python에서 조작할 수 있게 함
volume.SetMute(0, None) #뮤트 상태 제거 0:음소거 해제 1:음소거

# 볼륨 10칸 내리기
for _ in range(steps):
    volume.SetMasterVolumeLevelScalar(max(volume.GetMasterVolumeLevelScalar() - 0.01, 0.0), None)
# volume.GetMasterVolumeLevelScalar() : 현재 볼륨 값을 0.0 ~ 1.0 사이 실수 값으로 반환. 
# 0.0이 최소소. 0.01씩 감소시킴.

if volume.GetMasterVolumeLevelScalar() == 0.0:
    volume.SetMute(1, None) 
#만약 볼륨값이 0이라면 뮤트시켜서 소리가 안나게 함.    