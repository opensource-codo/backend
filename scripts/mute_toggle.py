from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL

devices = AudioUtilities.GetSpeakers() # 시스템에서 현재 기본 스피커(오디오 출력 장치)를 가져옴
interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None) # 해당 오디오 장치의 오디오 엔드포인트 볼륨 인터페이스를 활성화
volume = cast(interface, POINTER(IAudioEndpointVolume)) # COM 인터페이스를 ctypes 포인터 타입으로 변환하여 Python에서 조작할 수 있게 함

is_muted = volume.GetMute() #현재 뮤트값을 가져옴. 0이면 음소거 해제 1이면 음소거 상태.

if is_muted == 0: #소리가 나는 상태라면,
    volume.SetMute(1, None) #음소거로

if is_muted == 1: #음소거 상태라면,
    volume.SetMute(0, None) #소리가 나게