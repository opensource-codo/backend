from playwright.sync_api import sync_playwright
import time
#브라우저 정리
def update_chrome_with_shortcuts(browser_type="chromium"):
    with sync_playwright() as p:
        if browser_type == "chromium":
            browser = p.chromium.launch(headless=False)
        elif browser_type == "edge":
            browser = p.chromium.launch(channel="msedge", headless=False)
        else:
            print("지원하지 않는 브라우저 타입입니다.")
            return

        context = browser.new_context()
        page = context.new_page()

        # 새 탭 빈 페이지 열기
        page.goto("about:blank")

        # 크롬에서 Alt+F 키로 더보기 메뉴 열기 (Windows 기준)
        page.keyboard.press("Alt+F")
        time.sleep(1)

        #방향키로 도움말 위치까지 이동 (탭/방향키 조합 조절 필요)
        #도움말 메뉴 보통 맨 아래 근처, 아래 방향키 여러 번 누름
        for _ in range(2):
            page.keyboard.press("ArrowUp")
            print("up 버튼 클릭")
            time.sleep(0.1)

        #page.keyboard.press("Enter")
        #time.sleep(3)
    
        
        # 'Chrome 정보'가 새 창이나 새 탭으로 열릴 경우 약간 대기
        # 만약 새 탭 열린다면 전환 필요
        pages = context.pages
        if len(pages) > 1:
            info_page = pages[-1]
        else:
            info_page = page

        # 이후 창에서 업데이트 확인 및 '다시 시작' 버튼 클릭 자동화는
        # 실제 UI에 맞는 selector 사용해 가능 (아래 예시는 한글/영문 버튼 텍스트 기준)

        try:
            info_page.wait_for_selector("text=Chrome 정보", timeout=5000)
            info_page.click("text=Chrome 정보")
            print("'Chrome 정보' 버튼 클릭 완료")
        except:
            try:
                info_page.wait_for_selector("text=About Google Chrome", timeout=5000)
                info_page.click("text=About Google Chrome")
                print("About Google Chrome 버튼 클릭 완료")
            except:
                print("크롬 정보 버튼을 찾지 못했습니다. UI가 다를 수 있습니다.")

        time.sleep(5)  # 종료 대기
        browser.close()


if __name__ == "__main__":
    update_chrome_with_shortcuts("chromium")  # 또는 edge
