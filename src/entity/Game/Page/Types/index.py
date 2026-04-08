from src.entity.Game.Page.Types.Tabs.Contest import ContestTab
from src.entity.Game.Page.Types.Tabs.Gacha import GachaTab
from src.entity.Game.Page.Types.Tabs.Home import HomeTab
from src.entity.Game.Page.Types.Tabs.Idol import IdolTab
from src.entity.Game.Page.Types.Tabs.Communicate import CommunicateTab
from src.entity.Game.Page.Types.Tabs.SubMenu import SubMenu


class GamePageTypes:
    START_GAME = "START_GAME"
    LOADING = "LOADING"
    DOWNLOADING = "DOWNLOADING"
    UNKNOWN = "UNKNOWN"
    PRODUCER__MEMORY_SELECTION = "PRODUCER__MEMORY_SELECTION"
    PRODUCER__MEMORY_CANDIDATE_LIST = "PRODUCER__MEMORY_CANDIDATE_LIST"
    PRODUCER__MEMORY_DETAIL = "PRODUCER__MEMORY_DETAIL"
    PRODUCER__FINAL_CONFIRM = "PRODUCER__FINAL_CONFIRM"
    PRODUCER__FORMATION_DETAILS = "PRODUCER__FORMATION_DETAILS"
    #
    MAIN_MENU__GACHA = "MAIN_MENU__GACHA"
    MAIN_MENU__CONTEST = "MAIN_MENU__CONTEST"
    MAIN_MENU__HOME = "MAIN_MENU__HOME"
    MAIN_MENU__IDOL = "MAIN_MENU__IDOL"
    MAIN_MENU__COMMUNICATE = "MAIN_MENU__COMMUNICATE"
    #
    GACHA_TAB = GachaTab
    CONTEST_TAB = ContestTab
    HOME_TAB = HomeTab
    IDOL_TAB = IdolTab
    Communicate_TAB = CommunicateTab
    #
    SUB_MENU = SubMenu


