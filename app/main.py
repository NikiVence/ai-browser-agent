import os

from pathlib import Path



from agent.agent_loop import AgentLoop

from agent.tool_log import log_user

from browser.actions import BrowserActions

from browser.browser import Browser

from config import USER_DATA_DIR





def main():



    cdp = os.getenv("PLAYWRIGHT_CDP_URL", "").strip()



    if cdp:



        print("Режим CDP: подключение к уже запущенному Chrome:", cdp)

        print(

            "Запусти Chrome с remote debugging, например:\n"

            '  chrome.exe --remote-debugging-port=9222 --user-data-dir="D:\\chrome-profile"\n'

        )

    else:



        print("Профиль Playwright (куки/сессии):", Path(USER_DATA_DIR).resolve())



        exe = os.getenv("PLAYWRIGHT_EXECUTABLE", "").strip()



        channel = os.getenv("PLAYWRIGHT_CHANNEL", "").strip()



    print("Закрой окно браузера или Ctrl+C, чтобы выйти.\n")



    browser = Browser()



    actions = BrowserActions(browser)



    agent = AgentLoop(browser, actions)



    task = input("TASK: ").strip()



    if not task:



        print("Пустая задача — выход.")



        return



    log_user(task)



    agent.run(task)





if __name__ == "__main__":



    main()


