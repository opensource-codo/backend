import winshell
 #휴지통 비우기
try:
    # confirm=False : 비우기 전 확인 대화상자 표시 X
    # show_progress=False : 진행 막대 표시 X
    # sound=True : 비우기 효과음 재생
    winshell.recycle_bin().empty(confirm=True, show_progress=True, sound=False)
    print("휴지통을 성공적으로 비웠습니다!")
except:
    print("이미 휴지통이 비어 있습니다.")
