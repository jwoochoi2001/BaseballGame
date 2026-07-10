"""메인 애플리케이션: 화면(씬) 전환과 게임 루프."""
import math
import random

import pygame

from . import config as C
from . import field
from .assets import get_font
from .ui import Button, TextInput, draw_text
from .gamestate import LiveGame, resolve_batted_ball

# 구종 정의: 이름과 구속 범위(km/h). 같은 구종도 매번 구속이 조금씩 다르다.
PITCHES = {
    "패스트볼": dict(speed=(145, 153)),
    "슬라이더": dict(speed=(125, 132)),
    "커브": dict(speed=(112, 123)),
}
PITCH_KEYS_B = {pygame.K_1: "패스트볼", pygame.K_2: "슬라이더", pygame.K_3: "커브"}
PITCH_KEYS_A = {pygame.K_8: "패스트볼", pygame.K_9: "슬라이더", pygame.K_0: "커브"}
PITCH_LETTER_A = {"8": "패스트볼", "9": "슬라이더", "0": "커브"}
PITCH_LETTER_B = {"1": "패스트볼", "2": "슬라이더", "3": "커브"}

# 구속(km/h) -> 게이지 스윕 시간(초). 빠를수록 시간이 짧아(게이지가 빨라) 맞추기 어렵다.
GAUGE_SLOW_SPEED, GAUGE_SLOW_TIME = 112.0, 1.38   # 커브 최저(가장 느림)
GAUGE_FAST_SPEED, GAUGE_FAST_TIME = 153.0, 0.66   # 패스트볼 최고(가장 빠름)

# 파워 게이지: 커서가 좌→우로 스윕(속도는 구속에 따라 달라짐). 멈춘 구간이 파워.
# 게이지 구간(왼→오): (start, end, 파워min, 파워max, 색상, 라벨)
BLUE_Z = (58, 128, 240)
ORANGE_Z = (255, 140, 36)
CONTACT_MIN_T = 0.58   # 이 지점부터 컨택. 그 전(파랑)은 헛스윙
# 게이지 구간(왼→오): (start, end, 파워min, 파워max, 색상, 라벨)
GAUGE_ZONES = [
    (0.000, CONTACT_MIN_T, 0.10, 0.22, BLUE_Z,     None),    # 파랑: 헛스윙
    (CONTACT_MIN_T, 0.720, 0.48, 0.62, C.GOOD,     "HIT"),   # 초록: 컨택
    (0.720, 0.820, 0.60, 0.74, ORANGE_Z,           None),    # 주황: 강한 컨택
    (0.820, 0.852, 0.68, 0.82, C.ACCENT,           None),    # 빨강: 최강(가장 좁음)
    (0.852, 1.000, 0.28, 0.44, C.ACCENT2,         None),    # 노랑: 늦은 스윙
]
SWING_ANIM_SEC = 0.30

# 좌측 패널 위치(구종 선택 / S B O)
LEFT_PANEL_X = 14
PITCH_PANEL_Y = 112
PITCH_PANEL_H = 142
COUNT_PANEL_Y = PITCH_PANEL_Y + PITCH_PANEL_H + 10

BASEPATH = [field.HOME, field.B1, field.B2, field.B3, field.HOME]


class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(C.TITLE)
        self.screen = pygame.display.set_mode((C.WIDTH, C.HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True
        self.scene = MenuScene(self)

    def change_scene(self, scene):
        self.scene = scene

    def run(self):
        while self.running:
            dt = self.clock.tick(C.FPS) / 1000.0
            events = pygame.event.get()
            for e in events:
                if e.type == pygame.QUIT:
                    self.running = False
            self.scene.handle(events)
            self.scene.update(dt)
            self.scene.draw(self.screen)
            pygame.display.flip()
        pygame.quit()


# ============================================================ 게임 설명
HELP_LINES = [
    ("title", "히팅카운트"),
    ("body", "탑다운 시점의 야구 타격 게임입니다, 타이밍에 맞춰 스윙해 안타·홈런을 노려보세요"),
    ("gap", ""),
    ("head", "게임 모드"),
    ("body", "· 1인 게임 (타격 챌린지): 혼자 타격만 합니다, CPU가 랜덤 구종·구속으로 투구"),
    ("body", "· 2인 게임: 한 명은 투수(구종 선택), 한 명은 타자(스페이스바 타격)"),
    ("body", "  플레이어A(원정·파랑) 수비: [8] 패스트볼 [9] 슬라이더 [0] 커브"),
    ("body", "  플레이어B(홈·빨강) 수비: [1] 패스트볼 [2] 슬라이더 [3] 커브"),
    ("body", "  공수교대 시 역할·유니폼 색이 바뀝니다"),
    ("body", "· 경기 전 라인업 화면에서 팀·선수 이름, 좌타/우타를 설정할 수 있습니다"),
    ("body", "  2인 기본 팀 이름: 플레이어A(원정) / 플레이어B(홈)"),
    ("body", "  설정한 이름이 전광판·결과 화면에 표시됩니다"),
    ("gap", ""),
    ("head", "1인 모드 — 타격 챌린지"),
    ("body", "· 라운드마다 제한 아웃 안에 누적 목표 점수를 달성해야 다음 라운드 진출"),
    ("body", "· 타자 이름 기본값은 「플레이어」(라인업 화면에서 변경 가능)"),
    ("body", "· 점수: 안타 30 / 2루타 50 / 3루타 70 / 홈런 100 / 타점 1점당 +50"),
    ("body", "· 목표(누적): 1R 300 → 2R 700(+400) → 3R 1200(+500) → 4R 1800(+600) …"),
    ("body", "· 아웃: 1R 10개 → 라운드마다 1개 감소(최소 5개), 삼진·아웃·병살 모두 소모"),
    ("body", "· 목표 미달 + 아웃 소진 시 게임 종료 → 점수·클리어 라운드·탈락 라운드 표시"),
    ("body", "· 「다시하기」로 재도전, 「그만하기」로 메인 메뉴"),
    ("body", "· 상단 전광판: 라운드, 목표, 누적 점수, 진행 바, 남은 아웃"),
    ("body", "· 볼넷·주자 진루 규칙은 2인과 동일(득점·밀어내기는 챌린지 점수로 반영)"),
    ("body", "· 라운드 클리어 시 주자는 초기화됩니다"),
    ("gap", ""),
    ("head", f"2인 모드 — 경기 규칙 ({C.MAX_INNINGS}회)"),
    ("body", f"· {C.MAX_INNINGS}회까지, 연장 없음, {C.MAX_INNINGS}회 종료 후 동점이면 무승부"),
    ("body", f"· {C.MAX_INNINGS}회초 3아웃 후 홈팀이 이기고 있으면 9회말 없이 즉시 경기 종료"),
    ("body", f"· {C.MAX_INNINGS}회초 끝에 홈팀이 지거나 비기면 9회말 진행"),
    ("body", "· 9회말 홈팀이 1점이라도 앞서면 끝내기(홈팀 승리)"),
    ("body", "· 끝내기 시 경기 중 「끝내기 승리 !!」 멘트, 종료 화면에 「끝내기 승리! {홈팀명}」"),
    ("body", "· 9회말 3아웃까지 동점이면 무승부(연장·10회 없음)"),
    ("body", "· 9회말에 원정팀은 더 이상 공격하지 않으므로 승리 불가"),
    ("body", "  리드를 지키거나 동점으로 끝내는 것이 최선"),
    ("body", "· 파울: 파울라인 밖 착지·타구 각도 시 스트라이크(+1)"),
    ("body", "  2스트라이크 후 파울은 삼진 안 됨(카운트 유지)"),
    ("body", "· 3아웃마다 공수교대, 4볼 볼넷, 3스트라이크 삼진(루킹·헛스윙)"),
    ("body", "· 경기 종료 후 승패·라인스코어·승리팀 BEST PLAYER 표시"),
    ("gap", ""),
    ("head", "팀 색상"),
    ("body", "· 원정팀 = 파랑, 홈팀 = 빨강"),
    ("body", "· 공격 팀 색 = 타자·주자, 수비 팀 색 = 수비수·포수"),
    ("gap", ""),
    ("head", "타격 (타이밍 게이지)"),
    ("body", "· 스페이스바로 스윙, 하단 게이지 커서 위치가 타구 품질을 결정"),
    ("body", "· 구속이 빠를수록 게이지도 빠름(같은 구종도 매 투구마다 다름)"),
    ("body", "· 게이지를 끝까지 안 치면 50% 볼 / 50% 루킹 스트라이크"),
    ("gap", ""),
    ("head", "게이지 구간 (왼쪽 → 오른쪽)"),
    ("body", "· 파랑 (0~58%): 헛스윙 — 스윙하면 스트라이크"),
    ("body", "· 초록 (58~72%): 컨택 — 기본 안타"),
    ("body", "· 주황 (72~82%): 강한 컨택 — 장타 가능"),
    ("body", "· 빨강 (82~85%): 최강·가장 좁음 — 홈런 노리기"),
    ("body", "· 노랑 (85~100%): 늦은 스윙 — 맞지만 파워 약함"),
    ("gap", ""),
    ("head", "구종 & 구속 (km/h)"),
    ("body", "· 패스트볼 145~153 / 슬라이더 125~132 / 커브 112~123"),
    ("body", "· 직구 > 슬라이더 > 커브 순으로 게이지가 빠름"),
    ("body", "· 투구 시 좌측 S/B/O 패널 아래에 구종·구속이 표시됩니다"),
    ("gap", ""),
    ("head", "타구 결과"),
    ("body", "· 안타·2루타·3루타·홈런, 내야 안타, 실책 출루"),
    ("body", "· 홈런: 솔로/2·3·만루·그랜드슬램 멘트, 득점 시 +N점 표시"),
    ("body", "· 득점 안타: 「N타점 적시타」 멘트(안타·1루타·2루타 등)"),
    ("body", "· 내야: 땅볼 아웃·송구, 내야 직선타 아웃"),
    ("body", "· 외야: 뜬공 아웃(직선타도 외야수가 잡으면 플라이 아웃)"),
    ("body", "· 병살타(6-4-3 등): 2아웃, 만루 병살 시 3루 득점 + 2아웃 3루 1명"),
    ("body", "  (1·2인 모드 동일) 단, 3아웃으로 이닝이 끝나면 그 플레이 득점은 무효"),
    ("body", "· 희생플라이·깊은 뜬공 태그업: 2아웃 전 3루·2루 진루 가능"),
    ("body", "· 아웃 중 득점(병살 타점·희생플라이 등): 「+N점」 멘트"),
    ("gap", ""),
    ("head", "주자·볼넷 규칙"),
    ("body", "· 볼넷: 포스 진루, 1·2루 → 만루, 만루 볼넷(밀어내기) → 1득점 + 만루 유지"),
    ("body", "· 만루 볼넷·끝내기 볼넷 멘트: 「밀어내기」(득점 시 +N점)"),
    ("body", "· 1루 송구 땅볼 아웃: 1루 주자 있을 때만 연쇄 진루(3루 주자는 홈인)"),
    ("body", "· 2·3루만 있을 때 1루 송구: 주자 제자리(득점·진루 없음)"),
    ("body", "· 1루 주자 있을 때 2루 포스 아웃 송구 가능(3루 주자 있으면 홈인·득점)"),
    ("body", "· 내야 땅볼 처리 중 실책이 나올 수 있음(확률)"),
    ("gap", ""),
    ("head", "화면 UI"),
    ("body", "· 2인: 상단 라인스코어 전광판(이닝별 R/H/E/B), 우측 주자·아웃·타자"),
    ("body", "· 2인: 우측 타석 아래 현재 타자 기록(타수·안타·타점·홈런, 볼넷은 타수 제외)"),
    ("body", "· 1인: 상단 챌린지 전광판(라운드·목표·점수·아웃)"),
    ("body", "· 좌측 S/B/O 카운트, 우하단 「일시정지」 또는 ESC"),
    ("body", "· 타구 시 주자·수비·송구 애니메이션, 결과 배너 표시"),
    ("gap", ""),
    ("head", "조작"),
    ("body", "· 타격: 스페이스바"),
    ("body", "· 구종 선택(2인): A팀 8/9/0, B팀 1/2/3"),
    ("body", "· 일시정지: 우하단 버튼 또는 ESC → 계속하기 / 그만하기"),
    ("body", "· 게임 설명 스크롤: 마우스 휠 또는 ↑↓"),
    ("body", "· 메인 메뉴 「개발정보」에서 버전·개발자 정보 확인"),
]


ABOUT_BTN = (12, C.HEIGHT - 40, 92, 30)


def make_about_button():
    return Button(ABOUT_BTN, "개발정보", size=16, color=C.PANEL, hover=C.PANEL_LIGHT)


class AboutScene:
    def __init__(self, app, prev_scene):
        self.app = app
        self.prev_scene = prev_scene
        self.btn_back = Button((C.WIDTH // 2 - 100, C.HEIGHT - 72, 200, 50),
                               "돌아가기", size=26, color=C.PANEL, hover=C.GRAY)

    def handle(self, events):
        mouse = pygame.mouse.get_pos()
        self.btn_back.update(mouse)
        for e in events:
            if self.btn_back.clicked(e):
                self.app.change_scene(self.prev_scene)

    def update(self, dt):
        pass

    def draw(self, s):
        s.fill(C.DARK_PANEL)
        pw, ph = 420, 320
        px = (C.WIDTH - pw) // 2
        py = (C.HEIGHT - ph) // 2 - 20
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((18, 22, 32, 245))
        s.blit(panel, (px, py))
        pygame.draw.rect(s, C.ACCENT2, (px, py, pw, ph), width=3, border_radius=14)

        draw_text(s, "개발 정보", 34, C.WIDTH // 2, py + 44, C.WHITE,
                  center=True, bold=True)
        draw_text(s, C.TITLE, 24, C.WIDTH // 2, py + 88, C.ACCENT2,
                  center=True, bold=True)
        draw_text(s, f"버전 {C.VERSION}", 20, C.WIDTH // 2, py + 122,
                  C.LIGHT_GRAY, center=True)

        draw_text(s, "개발자", 18, C.WIDTH // 2, py + 168, C.GRAY, center=True)
        draw_text(s, C.DEVELOPER, 28, C.WIDTH // 2, py + 200, C.WHITE,
                  center=True, bold=True)

        draw_text(s, "이메일", 18, C.WIDTH // 2, py + 244, C.GRAY, center=True)
        draw_text(s, C.DEVELOPER_EMAIL, 20, C.WIDTH // 2, py + 274,
                  C.GOOD, center=True)

        self.btn_back.draw(s)


class HelpScene:
    def __init__(self, app):
        self.app = app
        self.scroll = 0
        self.content_top = 72
        self.content_bottom = C.HEIGHT - 78
        self.view_h = self.content_bottom - self.content_top
        self._line_h = []
        for kind, text in HELP_LINES:
            if kind == "gap":
                self._line_h.append(10)
            elif kind == "title":
                self._line_h.append(44)
            elif kind == "head":
                self._line_h.append(32)
            else:
                self._line_h.append(26)
        self.content_h = sum(self._line_h) + 24
        self.max_scroll = max(0, self.content_h - self.view_h)
        self.btn_back = Button((C.WIDTH // 2 - 100, C.HEIGHT - 62, 200, 50),
                               "돌아가기", size=26, color=C.PANEL, hover=C.GRAY)

    def handle(self, events):
        mouse = pygame.mouse.get_pos()
        self.btn_back.update(mouse)
        for e in events:
            if e.type == pygame.MOUSEWHEEL:
                self.scroll = max(0, min(self.max_scroll,
                                         self.scroll - e.y * 28))
            elif e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_DOWN, pygame.K_s):
                    self.scroll = min(self.max_scroll, self.scroll + 28)
                elif e.key in (pygame.K_UP, pygame.K_w):
                    self.scroll = max(0, self.scroll - 28)
            if self.btn_back.clicked(e):
                self.app.change_scene(MenuScene(self.app))

    def update(self, dt):
        pass

    def draw(self, s):
        s.fill(C.DARK_PANEL)
        pygame.draw.rect(s, C.PANEL, (24, 16, C.WIDTH - 48, 52), border_radius=10)
        draw_text(s, "게임 설명", 32, C.WIDTH // 2, 42, C.WHITE, center=True, bold=True)

        clip = pygame.Rect(32, self.content_top, C.WIDTH - 64, self.view_h)
        s.set_clip(clip)
        y = self.content_top + 8 - self.scroll
        for (kind, text), lh in zip(HELP_LINES, self._line_h):
            if kind == "gap":
                y += lh
                continue
            if kind == "title":
                draw_text(s, text, 28, C.WIDTH // 2, y + lh // 2,
                          C.ACCENT2, center=True, bold=True)
            elif kind == "head":
                draw_text(s, text, 22, 48, y + lh // 2, C.GOOD, bold=True)
            else:
                draw_text(s, text, 17, 48, y + lh // 2, C.LIGHT_GRAY)
            y += lh
        s.set_clip(None)

        if self.max_scroll > 0:
            bar_x = C.WIDTH - 22
            bar_top = self.content_top + 4
            bar_h = self.view_h - 8
            pygame.draw.rect(s, (40, 44, 56), (bar_x, bar_top, 6, bar_h), border_radius=3)
            thumb_h = max(24, int(bar_h * self.view_h / self.content_h))
            thumb_y = bar_top + int((bar_h - thumb_h) * self.scroll / self.max_scroll)
            pygame.draw.rect(s, C.LIGHT_GRAY, (bar_x, thumb_y, 6, thumb_h), border_radius=3)
            draw_text(s, "스크롤: 휠 / ↑↓", 14, C.WIDTH // 2,
                      self.content_bottom - 6, C.GRAY, center=True)

        self.btn_back.draw(s)


# ============================================================ 시작 화면
class MenuScene:
    def __init__(self, app):
        self.app = app
        self.t = 0.0
        cx = C.WIDTH // 2
        self.btn_1p = Button((cx - 180, 320, 360, 70), "1인 게임 (타격 챌린지)", size=28)
        self.btn_2p = Button((cx - 180, 405, 360, 70), "2인 게임 (투수 vs 타자)", size=28)
        self.btn_help = Button((cx - 180, 490, 360, 58), "게임 설명", size=26,
                               color=C.PANEL, hover=C.PANEL_LIGHT)
        self.btn_quit = Button((cx - 90, 575, 180, 54), "종료", size=26,
                               color=C.PANEL, hover=C.GRAY)
        self.btn_about = make_about_button()

    def handle(self, events):
        mouse = pygame.mouse.get_pos()
        for b in (self.btn_1p, self.btn_2p, self.btn_help, self.btn_quit,
                  self.btn_about):
            b.update(mouse)
        for e in events:
            if self.btn_1p.clicked(e):
                self.app.change_scene(LineupScene(self.app, one_player=True))
            elif self.btn_2p.clicked(e):
                self.app.change_scene(LineupScene(self.app, one_player=False))
            elif self.btn_help.clicked(e):
                self.app.change_scene(HelpScene(self.app))
            elif self.btn_about.clicked(e):
                self.app.change_scene(AboutScene(self.app, self))
            elif self.btn_quit.clicked(e):
                self.app.running = False

    def update(self, dt):
        self.t += dt

    def draw(self, s):
        s.fill(C.DARK_PANEL)
        pygame.draw.rect(s, C.GRASS, (0, 0, C.WIDTH, 220))
        pygame.draw.rect(s, C.GRASS_DARK, (0, 200, C.WIDTH, 24))
        field.draw_menu_batter(s, self.t)
        draw_text(s, "히팅카운트", 64, C.WIDTH // 2, 88,
                  C.WHITE, center=True, bold=True)
        for b in (self.btn_1p, self.btn_2p, self.btn_help, self.btn_quit,
                  self.btn_about):
            b.draw(s)


# ============================================================ 라인업 설정
class LineupScene:
    def __init__(self, app, one_player):
        self.app = app
        self.one_player = one_player
        self.inputs = []
        self.team_inputs = []
        self.hand_btns = []
        if one_player:
            # 1인: 타자 한 명만 설정
            self.names = [C.DEFAULT_1P_BATTER]
            self.right = [C.DEFAULT_1P_RIGHT]
            cx = C.WIDTH // 2
            self.inputs.append(TextInput((cx - 160, 320, 320, 56),
                                         text=self.names[0], max_len=8))
            self.hand_btns.append(Button((cx - 80, 410, 160, 52),
                                         "우타" if self.right[0] else "좌타",
                                         size=26))
        else:
            # 2인: 팀 이름(1·3번 행 우측) + 1~9번 라인업
            self.names = list(C.DEFAULT_LINEUP)
            self.right = list(C.DEFAULT_RIGHT)
            self.lineup_top = 200
            team_x, team_w, team_h = 688, 220, 42
            self.team_inputs.append(
                TextInput((team_x, self.lineup_top, team_w, team_h),
                          text=C.DEFAULT_TEAM_AWAY, max_len=8))
            self.team_inputs.append(
                TextInput((team_x, self.lineup_top + 104, team_w, team_h),
                          text=C.DEFAULT_TEAM_HOME, max_len=8))
            for i in range(9):
                row_y = self.lineup_top + i * 52
                self.inputs.append(TextInput((300, row_y, 240, 42),
                                             text=self.names[i], max_len=8))
                self.hand_btns.append(Button((560, row_y, 110, 42),
                                             "우타" if self.right[i] else "좌타",
                                             size=22))
            team_btn_y = self.lineup_top + 104 + team_h + 18
            self.btn_start = Button((team_x, team_btn_y, team_w, 58),
                                    "경기 시작", size=28, color=C.ACCENT,
                                    hover=C.GOOD)
            last_row_bottom = self.lineup_top + 8 * 52 + 42
            self.btn_back = Button((40, last_row_bottom + 12, 140, 54), "뒤로",
                                   size=24, color=C.PANEL, hover=C.GRAY)
        if one_player:
            self.btn_start = Button((C.WIDTH // 2 - 110, 640, 220, 60),
                                    "경기 시작", size=30, color=C.ACCENT,
                                    hover=C.GOOD)
            self.btn_back = Button((40, 640, 140, 54), "뒤로", size=24,
                                   color=C.PANEL, hover=C.GRAY)

    def handle(self, events):
        mouse = pygame.mouse.get_pos()
        for b in self.hand_btns + [self.btn_start, self.btn_back]:
            b.update(mouse)
        for e in events:
            for inp in self.team_inputs + self.inputs:
                inp.handle(e)
            for i, b in enumerate(self.hand_btns):
                if b.clicked(e):
                    self.right[i] = not self.right[i]
                    b.text = "우타" if self.right[i] else "좌타"
            if self.btn_back.clicked(e):
                self.app.change_scene(MenuScene(self.app))
            elif self.btn_start.clicked(e):
                self._start()

    def _start(self):
        names = [inp.text.strip() or (C.DEFAULT_1P_BATTER if self.one_player
                                     else C.DEFAULT_LINEUP[i])
                 for i, inp in enumerate(self.inputs)]
        if self.one_player:
            lineups = [list(C.DEFAULT_LINEUP), names]
            team_names = ["상대팀", "우리팀"]
            rights = [list(C.DEFAULT_RIGHT), list(self.right)]
        else:
            lineups = [names, list(names)]
            team_names = [
                self.team_inputs[0].text.strip() or C.DEFAULT_TEAM_AWAY,
                self.team_inputs[1].text.strip() or C.DEFAULT_TEAM_HOME,
            ]
            rights = [list(self.right), list(self.right)]
        game = LiveGame(self.one_player, lineups, team_names)
        game.right = rights
        self.app.change_scene(PlayScene(self.app, game))

    def update(self, dt):
        pass

    def draw(self, s):
        s.fill(C.DARK_PANEL)
        if self.one_player:
            draw_text(s, "1인 게임 - 타격 챌린지", 40, C.WIDTH // 2, 90,
                      C.WHITE, center=True, bold=True)
            draw_text(s, "제한 아웃 안에 목표 점수를 달성하는 솔로 모드", 22,
                      C.WIDTH // 2, 150, C.LIGHT_GRAY, center=True)
            draw_text(s, "타자 이름 (클릭해서 수정)", 22, C.WIDTH // 2, 290,
                      C.ACCENT2, center=True, bold=True)
            self.inputs[0].draw(s)
            self.hand_btns[0].draw(s)
        else:
            draw_text(s, "2인 게임 - 라인업 설정", 40, C.WIDTH // 2, 52,
                      C.WHITE, center=True, bold=True)
            draw_text(s, "타순", 22, 210, self.lineup_top - 30, C.LIGHT_GRAY, center=True)
            draw_text(s, "선수 이름 (클릭해서 수정)", 22, 420, self.lineup_top - 30,
                      C.LIGHT_GRAY, center=True)
            draw_text(s, "타격", 22, 615, self.lineup_top - 30, C.LIGHT_GRAY, center=True)
            draw_text(s, "팀 이름", 22, 798, self.lineup_top - 30, C.LIGHT_GRAY, center=True)
            draw_text(s, "원정·파랑", 16, 798, self.lineup_top - 10,
                      C.TEAM_AWAY, center=True, bold=True)
            draw_text(s, "홈·빨강", 16, 798, self.lineup_top + 94,
                      C.TEAM_HOME, center=True, bold=True)
            for inp in self.team_inputs:
                inp.draw(s)
            for i in range(9):
                row_y = self.lineup_top + i * 52
                draw_text(s, f"{i + 1}번", 26, 210, row_y + 21, C.ACCENT2,
                          center=True, bold=True)
                self.inputs[i].draw(s)
                self.hand_btns[i].draw(s)
        self.btn_start.draw(s)
        self.btn_back.draw(s)


# ============================================================ 경기 플레이
P_SELECT = "select"
P_READY = "ready"
P_PITCH = "pitch"
P_BATTED = "batted"
P_RESULT = "result"
P_INNING_CHANGE = "inning_change"
P_ROUND_CLEAR = "round_clear"


def _lerp(a, b, p):
    return (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)


_OUTFIELD = ("좌익수", "중견수", "우익수")
_OUTFIELD_SHIFT_MIN_FT = 115.0


def _outfield_play(plan):
    """착지가 외야이거나 외야수가 처리하는 플레이."""
    if plan["kind"] == "foul":
        return False
    land = plan["landing"]
    dist = field.dist_ft(field.HOME, land)
    if plan["kind"] == "hr":
        return True
    if plan.get("field_by") in _OUTFIELD:
        return True
    if plan["ball_type"] == "fly" and dist >= _OUTFIELD_SHIFT_MIN_FT:
        return True
    if plan["ball_type"] == "ground" and dist >= 140:
        return True
    return False


def _outfield_shift_frac(name, landing):
    """비담당 외야수: 홈→착지 방향과의 정렬도에 따라 이동 비율."""
    hx, hy = field.FIELDERS_HOME[name]
    lx, ly = landing
    ld = math.hypot(lx, ly)
    hd = math.hypot(hx, hy)
    if ld < 1e-6 or hd < 1e-6:
        return 0.2
    alignment = (hx / hd) * (lx / ld) + (hy / hd) * (ly / ld)
    return min(0.44, 0.18 + 0.26 * max(0.0, alignment))


def _runner_pos(start_idx, end_idx, p):
    if end_idx == start_idx:
        return BASEPATH[start_idx]
    fp = start_idx + (end_idx - start_idx) * max(0.0, min(1.0, p))
    i0 = int(math.floor(fp))
    i1 = min(i0 + 1, 4)
    return _lerp(BASEPATH[i0], BASEPATH[i1], fp - i0)


class PlayScene:
    def __init__(self, app, game: LiveGame):
        self.app = app
        self.game = game
        self.phase = None
        self.strikes = 0
        self.balls = 0
        self.timer = 0.0

        self.pitch_name = "패스트볼"
        self.pitch_speed = 0
        self.t = 0.0
        self.swung = False
        self.swing_progress = None
        self.plan = None

        # 타구 애니메이션 상태
        self.anim_t = 0.0
        self.anim_total = 1.0
        self.t_flight = 1.0
        self.ball_pos = field.HOME
        self.ball_h = 0.0
        self.fielder_positions = dict(field.FIELDERS_HOME)
        self.runner_tracks = []   # (start_idx, end_idx, out, color)

        self.result_text = ""
        self.result_color = C.WHITE
        self._re_pitch = False
        self.cpu_target = None    # CPU 타자가 스윙할 목표 타이밍

        self.paused = False
        cx = C.WIDTH // 2
        self.btn_resume = Button((cx - 120, C.HEIGHT // 2 - 8, 240, 52),
                                 "계속하기", size=26, color=C.GOOD, hover=C.ACCENT2)
        self.btn_quit_game = Button((cx - 120, C.HEIGHT // 2 + 58, 240, 52),
                                    "그만하기", size=26, color=C.ACCENT, hover=C.PANEL_LIGHT)
        self.btn_menu = Button((C.WIDTH - 96, C.HEIGHT - 40, 84, 32), "일시정지",
                               size=18, color=C.PANEL, hover=C.GRAY)
        self._begin_at_bat()

    # ------------------------------------------------ 흐름
    def _human_batting(self):
        """현재 타석을 사람이 조작하는가."""
        return not self.game.one_player or self.game.batting_team == 1

    def _pitch_keys(self):
        """2인 모드 수비 팀별 구종 선택 키 (A=8/9/0, B=1/2/3)."""
        if self.game.defending_team == 0:
            return PITCH_KEYS_A
        return PITCH_KEYS_B

    def _pitch_from_input(self, key=None, text=None):
        """KEYDOWN·TEXTINPUT 모두에서 구종 이름을 해석 (macOS 호환)."""
        if key is not None:
            keys = self._pitch_keys()
            if key in keys:
                return keys[key]
        if text:
            ch = text.lower() if self.game.defending_team == 0 else text
            letters = PITCH_LETTER_A if self.game.defending_team == 0 else PITCH_LETTER_B
            return letters.get(ch)
        return None

    def _try_select_pitch(self, event):
        if self.phase != P_SELECT or self.game.one_player:
            return False
        pitch = None
        if event.type == pygame.KEYDOWN:
            pitch = self._pitch_from_input(key=event.key, text=event.unicode)
        elif event.type == pygame.TEXTINPUT:
            pitch = self._pitch_from_input(text=event.text)
        if not pitch:
            return False
        self.pitch_name = pitch
        self._roll_speed()
        self.phase = P_READY
        self.timer = 0.45
        return True

    def _team_color(self, team_idx):
        return C.TEAM_COLORS[team_idx]

    def _begin_at_bat(self):
        self.strikes = 0
        self.balls = 0
        self._begin_pitch()

    def _begin_pitch(self):
        self.t = 0.0
        self.swung = False
        self.swing_progress = None
        self.plan = None
        self.cpu_target = None
        self.fielder_positions = dict(field.FIELDERS_HOME)
        if self.game.is_over():
            self.app.change_scene(GameOverScene(self.app, self.game))
            return
        # 투수: 1인 모드는 항상 CPU 랜덤 구종, 2인은 수비 플레이어가 선택
        if self.game.one_player:
            self.pitch_name = random.choice(list(PITCHES.keys()))
            self._roll_speed()
            self.phase = P_READY
            self.timer = 0.55
        else:
            self.phase = P_SELECT

    def _roll_speed(self):
        lo, hi = PITCHES[self.pitch_name]["speed"]
        self.pitch_speed = random.randint(lo, hi)

    def _pitch_time(self):
        # 게이지 스윕 시간 = 공 도달 시간. 실제 던진 구속이 빠를수록 게이지도 빠르다.
        # (같은 구종이라도 매 투구 구속이 달라 미세하게 속도가 바뀐다)
        spd = max(GAUGE_SLOW_SPEED, min(GAUGE_FAST_SPEED, self.pitch_speed))
        frac = (spd - GAUGE_SLOW_SPEED) / (GAUGE_FAST_SPEED - GAUGE_SLOW_SPEED)
        return GAUGE_SLOW_TIME + (GAUGE_FAST_TIME - GAUGE_SLOW_TIME) * frac

    def _zone_power(self, pos):
        """커서 위치(pos)가 속한 구간의 파워를 반환. 구간 밖이면 None."""
        for a, b, pmin, pmax, _color, _label in GAUGE_ZONES:
            if a <= pos < b:
                base = random.uniform(pmin, pmax)
                # 빨강(최강·가장 좁은 구간): 파워는 높지만 변동이 커서 홈런 보장 없음
                if _color == C.ACCENT:
                    base *= random.uniform(0.82, 0.98)
                return base
        return None

    def _is_peak_zone(self, pos):
        """빨강 최강 구간 여부(발사각 분산용)."""
        for a, b, _pmin, _pmax, color, _label in GAUGE_ZONES:
            if a <= pos < b:
                return color == C.ACCENT
        return False

    # ------------------------------------------------ 스윙 판정
    def _do_swing(self):
        if self.swung or self.phase != P_PITCH:
            return
        self.swung = True
        # 파랑(헛스윙) 구간에서 스윙 = 헛스윙
        if self.t < CONTACT_MIN_T:
            self._register_strike("swing")
            return
        power = self._zone_power(self.t)
        if power is None:
            # 게이지를 지나쳐 스윙(안전장치): 헛스윙
            self._register_strike("swing")
            return
        # 발사각: 무작위성이 커서 결과가 다양함 (빨강 최강 구간도 홈런 보장 없음)
        if self._is_peak_zone(self.t):
            launch = random.gauss(24, 22)
        else:
            launch = random.gauss(18, 16)
        launch = max(0.0, min(62.0, launch))
        # 방향: 약간의 당김 성향 + 무작위
        pull = -1.0 if self.game.batter_is_right() else 1.0
        spray = pull * random.uniform(0, 16) + random.gauss(0, 20)
        spray = max(-55.0, min(55.0, spray))

        plan = resolve_batted_ball(power, spray, launch,
                                   self.game.bases, self.game.outs_for_rules)
        plan["bases_at_pitch"] = list(self.game.bases)
        if plan["kind"] == "foul":
            self.plan = plan
            self._start_batted()
            return
        self.plan = plan
        self._start_batted()

    def _register_ball(self):
        self.balls += 1
        if self.balls >= 4:
            runs = self.game.walk()
            gain = self.game.solo_last_gain if self.game.one_player else runs
            label = "밀어내기" if runs else "볼넷!"
            if self.game.walk_off:
                lines = ["끝내기 승리 !!", label]
                self._show_result("\n".join(lines), C.ACCENT2, long_display=True)
            elif self.game.one_player:
                lines = [label]
                if gain:
                    lines.append(f"+{gain}점")
                self._show_result("\n".join(lines), C.GOOD, long_display=bool(gain))
            else:
                extra = f"\n+{runs}점" if runs else ""
                self._show_result(f"{label}{extra}", C.GOOD, long_display=bool(runs))
        else:
            self._show_result(f"볼 (B{self.balls})", C.GOOD, re_pitch=True)

    def _register_strike(self, kind="swing"):
        """kind: 'swing'(헛스윙), 'look'(안 휘두름), 'foul'(파울)."""
        if kind == "foul":
            # 파울은 2스트라이크 이후엔 카운트 유지(삼진 없음)
            if self.strikes < 2:
                self.strikes += 1
            self._show_result("파울", C.ACCENT2, re_pitch=True)
            return
        self.strikes += 1
        if self.strikes >= 3:
            self.game.strikeout()
            if self.game.is_over() and self.game.skipped_bottom_9th:
                self._show_result("경기 종료", C.ACCENT2, long_display=True)
            elif self.game.is_over() and self.game.game_tied:
                self._show_result("경기 종료\n무승부", C.ACCENT2,
                                  long_display=True)
            elif kind == "look":
                self._show_result("루킹 삼진!", C.ACCENT)
            else:
                self._show_result("삼진 아웃!", C.ACCENT)
        else:
            self._show_result(f"스트라이크 (S{self.strikes})", C.ACCENT2,
                              re_pitch=True)

    # ------------------------------------------------ 타구 애니메이션 준비
    def _start_batted(self):
        plan = self.plan
        self.phase = P_BATTED
        self.anim_t = 0.0
        self.fielder_positions = dict(field.FIELDERS_HOME)
        bt = plan["ball_type"]
        if plan["kind"] == "foul":
            self.t_flight = 1.05
            self.anim_total = self.t_flight + 0.42
            self._dp_throw = False
            self._has_throw = False
        else:
            self.t_flight = {"ground": 1.0, "fly": 1.35}.get(bt, 1.35)
            if bt == "fly" and plan["kind"] == "hr":
                self.t_flight = 1.7
            throw = plan.get("throw_to") is not None and plan["kind"] in ("out", "hit", "error")
            self._dp_throw = bool(plan.get("double_play"))
            self._has_throw = throw and bt == "ground"
            self._dp_t1 = 0.34
            self._dp_t2 = 0.34
            if plan.get("tag_up"):
                self.anim_total = self.t_flight + 1.0
            elif self._dp_throw:
                self.anim_total = self.t_flight + self._dp_t1 + self._dp_t2 + 0.18
            else:
                self.anim_total = self.t_flight + (0.7 if self._has_throw else 0.4)

        # 주자 트랙 구성
        self.runner_tracks = self._build_tracks(plan)

    def _build_tracks(self, plan):
        # 트랙: (시작루, 도착루, 아웃여부, 색, 출발시점 t0)
        tracks = []
        b = plan.get("bases_at_pitch", self.game.bases)
        kind = plan["kind"]
        n = plan.get("bases", 0)
        off = self._team_color(self.game.batting_team)
        if kind in ("hit", "hr", "error"):
            # 기존 주자
            for i, on in enumerate(b):
                if on:
                    tracks.append((i + 1, min(4, i + 1 + n), False, off, 0.0))
            tracks.append((0, min(4, n), False, off, 0.0))  # 타자
        elif kind == "out":
            if plan.get("double_play"):
                tracks.append((0, 1, True, C.GRAY, 0.0))
                if b[0]:
                    tracks.append((1, 2, True, C.GRAY, 0.0))
                if b[2]:
                    tracks.append((3, 4, False, off, 0.0))
                if b[1]:
                    tracks.append((2, 3, False, off, 0.0))
            elif plan.get("tag_up"):
                # 깊은 뜬공 아웃: 잡은 뒤(후반) 2·3루 주자 태그업 진루
                if b[2]:
                    tracks.append((3, 4, False, off, 0.6))   # 3루→홈
                if b[1]:
                    tracks.append((2, 3, False, off, 0.6))   # 2루→3루
                if b[0]:
                    tracks.append((1, 1, False, off, 0.0))   # 1루 정지
            elif plan.get("force_out_2nd"):
                if b[0]:
                    tracks.append((1, 2, True, C.GRAY, 0.0))
                if b[1]:
                    tracks.append((2, 3, False, off, 0.0))
                tracks.append((0, 1, False, off, 0.0))
                if b[2]:
                    tracks.append((3, 4, False, off, 0.0))
            elif plan.get("out_at_first"):
                tracks.append((0, 1, True, C.GRAY, 0.0))
                if b[0]:
                    tracks.append((1, 2, False, off, 0.0))
                    if b[1]:
                        tracks.append((2, 3, False, off, 0.0))
                elif b[1]:
                    tracks.append((2, 3, False, off, 0.0))
                if b[2]:
                    tracks.append((3, 4, False, off, 0.0))
            else:
                # 땅볼/뜬공 아웃: 타자 1루로 뛰다 아웃, 주자 정지
                tracks.append((0, 1, True, C.GRAY, 0.0))
                for i, on in enumerate(b):
                    if on:
                        tracks.append((i + 1, i + 1, False, off, 0.0))
        return tracks

    def _finish_batted(self):
        if self.plan["kind"] == "foul":
            self._register_strike("foul")
            return
        self.game.apply_plan(self.plan)
        if self.game.is_over() and self.game.skipped_bottom_9th:
            self._show_result("경기 종료", C.ACCENT2, long_display=True)
            return
        if self.game.is_over() and self.game.game_tied:
            self._show_result("경기 종료\n무승부", C.ACCENT2, long_display=True)
            return
        text, col = self._play_result_message(self.plan)
        wo = self.game.walk_off
        scored = (self.game.solo_last_gain if self.game.one_player
                  else self.game.last_runs) > 0
        long_display = wo or self.plan["kind"] == "hr" or (
            scored and self.plan["kind"] == "out")
        self._show_result(text, col, long_display=long_display)

    def _play_result_message(self, plan):
        if self.game.one_player:
            return self._solo_result_message(plan)
        runs = self.game.last_runs
        if self.game.walk_off:
            return "끝내기 승리 !!", C.ACCENT2
        if plan["kind"] == "hr":
            title = plan.get("hr_title", "HOME RUN!")
            sub = plan.get("hr_sub", "")
            lines = [title, sub]
            if runs:
                lines.append(f"+{runs}점")
            return "\n".join(lines), C.GOOD
        if plan["kind"] == "hit":
            lines = [plan["label"]]
            if runs:
                lines.append(f"{runs}타점 적시타")
            return "\n".join(lines), C.GOOD
        if plan["kind"] == "error":
            lines = [plan["label"]]
            if runs:
                lines.append(f"+{runs}점")
            return "\n".join(lines), C.GOOD
        # 아웃(병살·희생플라이·태그업 등) 중 득점이 있으면 표시
        lines = [plan["label"]]
        if runs:
            lines.append(f"+{runs}득점")
        col = C.ACCENT
        return "\n".join(lines), col

    def _solo_result_message(self, plan):
        gain = self.game.solo_last_gain
        runs = self.game.last_runs
        if plan["kind"] == "hr":
            lines = [plan.get("hr_title", "HOME RUN!"), plan.get("hr_sub", "")]
            if gain:
                lines.append(f"+{gain}점")
            return "\n".join(lines), C.GOOD
        lines = [plan["label"]]
        if runs > 0:
            lines.append(f"+{runs}득점")
        if gain > 0:
            lines.append(f"+{gain}점")
        col = C.GOOD if (gain > 0 or runs > 0) else C.ACCENT
        return "\n".join(lines), col

    def _after_play_result(self):
        if self.game.one_player and self.game.solo_round_clear_pending:
            self.game.solo_round_clear_pending = False
            self.phase = P_ROUND_CLEAR
            self.timer = 2.6
            return
        if self.game.is_over():
            self.app.change_scene(GameOverScene(self.app, self.game))
            return
        if not self.game.one_player and self.game.pending_inning_change:
            self.game.pending_inning_change = False
            self.phase = P_INNING_CHANGE
            self.timer = 2.0
        else:
            self._begin_at_bat()

    def _show_result(self, text, color, re_pitch=False, long_display=False):
        self.result_text = text
        self.result_color = color
        self.phase = P_RESULT
        self.timer = 2.8 if long_display else 1.5
        self._re_pitch = re_pitch

    # ------------------------------------------------ 이벤트/업데이트
    def handle(self, events):
        mouse = pygame.mouse.get_pos()
        if self.paused:
            self.btn_resume.update(mouse)
            self.btn_quit_game.update(mouse)
            for e in events:
                if self.btn_resume.clicked(e):
                    self.paused = False
                elif self.btn_quit_game.clicked(e):
                    self.app.change_scene(MenuScene(self.app))
            return

        self.btn_menu.update(mouse)
        for e in events:
            if self.btn_menu.clicked(e):
                self.paused = True
                return
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.paused = True
                    return
                if self._try_select_pitch(e):
                    pass
                elif e.key == pygame.K_SPACE and self.phase == P_PITCH \
                        and self._human_batting():
                    if self.swing_progress is None:
                        self.swing_progress = 0.0
                    self._do_swing()
            elif e.type == pygame.TEXTINPUT:
                self._try_select_pitch(e)

    def update(self, dt):
        if self.paused:
            return

        if self.swing_progress is not None and self.swing_progress < 1.0:
            self.swing_progress = min(1.0, self.swing_progress + dt / SWING_ANIM_SEC)

        if self.phase == P_READY:
            self.timer -= dt
            if self.timer <= 0:
                self.phase = P_PITCH
        elif self.phase == P_PITCH:
            self.t += dt / self._pitch_time()
            # CPU 타자(1인 모드 상대팀) 자동 스윙
            if self.cpu_target is not None and not self.swung \
                    and self.t >= self.cpu_target:
                self.swing_progress = 0.0
                self._do_swing()
            # 게이지 끝까지 안 치면 노스윙 — 50% 볼 / 50% 루킹 스트라이크
            if self.t >= 1.0 and not self.swung:
                if random.random() < 0.5:
                    self._register_ball()
                else:
                    self._register_strike("look")
        elif self.phase == P_BATTED:
            self.anim_t += dt
            self._update_batted()
            if self.anim_t >= self.anim_total:
                self._finish_batted()
        elif self.phase == P_RESULT:
            self.timer -= dt
            if self.timer <= 0:
                if self.game.is_over():
                    self.app.change_scene(GameOverScene(self.app, self.game))
                elif self._re_pitch:
                    self._begin_pitch()
                else:
                    self._after_play_result()
        elif self.phase == P_INNING_CHANGE:
            self.timer -= dt
            if self.timer <= 0:
                self._begin_at_bat()
        elif self.phase == P_ROUND_CLEAR:
            self.timer -= dt
            if self.timer <= 0:
                self._begin_at_bat()

    def _update_batted(self):
        plan = self.plan
        land = plan["landing"]
        tf = self.t_flight
        p = min(1.0, self.anim_t / tf)

        # 공 위치
        if self._dp_throw:
            t1, t2 = self._dp_t1, self._dp_t2
            mid = plan["dp_mid"]
            final = plan["throw_to"]
            at = self.anim_t
            if at <= tf:
                self.ball_pos = _lerp(field.HOME, land, p)
                self.ball_h = 4.0
            elif at <= tf + t1:
                tp = (at - tf) / t1
                self.ball_pos = _lerp(land, mid, tp)
                self.ball_h = 12.0 * math.sin(math.pi * tp)
            else:
                tp = min(1.0, (at - tf - t1) / t2)
                self.ball_pos = _lerp(mid, final, tp)
                self.ball_h = 10.0 * math.sin(math.pi * tp)
        elif self._has_throw and self.anim_t > tf:
            tp = min(1.0, (self.anim_t - tf) / 0.55)
            self.ball_pos = _lerp(land, plan["throw_to"], tp)
            self.ball_h = 12.0 * math.sin(math.pi * tp)
        else:
            self.ball_pos = _lerp(field.HOME, land, p)
            if plan["ball_type"] == "foul":
                self.ball_h = 55.0 * math.sin(math.pi * p)
            elif plan["ball_type"] == "fly":
                self.ball_h = 120.0 * math.sin(math.pi * p) * (1.4 if plan["kind"] == "hr" else 1.0)
            else:
                self.ball_h = 4.0

        # 담당 수비수 이동
        fb = plan.get("field_by")
        if fb and fb in self.fielder_positions:
            home_pos = field.FIELDERS_HOME[fb]
            if plan["kind"] == "out":
                fp = min(1.0, p * 1.05)
            else:
                fp = min(1.0, self.anim_t / max(0.3, self.anim_total))
            self.fielder_positions[fb] = _lerp(home_pos, land, fp)
            if self._dp_throw and self.anim_t > tf:
                self.fielder_positions[fb] = land

        # 외야: 담당 외야수 외 인접 수비수도 착지 방향으로 살짝 이동
        if _outfield_play(plan):
            shift_p = min(1.0, p * 1.12)
            for name in _OUTFIELD:
                if name == fb:
                    continue
                home = field.FIELDERS_HOME[name]
                frac = _outfield_shift_frac(name, land)
                self.fielder_positions[name] = _lerp(home, land, frac * shift_p)

        if self._dp_throw:
            relay = plan["dp_relay"]
            mid = plan["dp_mid"]
            final = plan["throw_to"]
            t1, t2 = self._dp_t1, self._dp_t2
            relay_home = field.FIELDERS_HOME[relay]

            # 릴레이 수비수: 2루 커버 → 1루 송구
            if self.anim_t <= tf:
                rp = min(1.0, self.anim_t / max(0.12, tf * 0.88))
                self.fielder_positions[relay] = _lerp(relay_home, mid, rp)
            elif self.anim_t <= tf + t1 + t2 * 0.45:
                self.fielder_positions[relay] = mid
            else:
                tp = min(1.0, (self.anim_t - tf - t1 - t2 * 0.45) / (t2 * 0.55))
                self.fielder_positions[relay] = _lerp(
                    mid, _lerp(mid, final, 0.25), tp * 0.35)

            # 1루수: 1루 베이스 커버 (1루수가 직접 건진 3-6-3는 송구 후 복귀)
            if fb == "1루수":
                if self.anim_t > tf + t1:
                    tp = min(1.0, (self.anim_t - tf - t1) / t2)
                    self.fielder_positions["1루수"] = _lerp(land, final, tp)
            else:
                rp1 = min(1.0, self.anim_t / max(0.1, tf * 0.72))
                self.fielder_positions["1루수"] = _lerp(
                    field.FIELDERS_HOME["1루수"], final, rp1)
        elif self._has_throw and plan.get("force_out_2nd"):
            relay = plan.get("fc_relay", "2루수")
            relay_home = field.FIELDERS_HOME[relay]
            if fb == relay:
                if self.anim_t > tf:
                    tp = min(1.0, (self.anim_t - tf) / 0.55)
                    self.fielder_positions[relay] = _lerp(land, field.B2, tp)
            else:
                rp = min(1.0, self.anim_t / max(0.1, tf * 0.85))
                self.fielder_positions[relay] = _lerp(relay_home, field.B2, rp)
        elif self._has_throw and plan.get("throw_to") == field.B1:
            # 1루 송구 아웃: 1루수가 베이스를 밟으며 포구
            if fb == "1루수":
                if self.anim_t > tf:
                    tp = min(1.0, (self.anim_t - tf) / 0.55)
                    self.fielder_positions["1루수"] = _lerp(land, field.B1, tp)
            else:
                rp = min(1.0, self.anim_t / max(0.1, tf * 0.85))
                self.fielder_positions["1루수"] = _lerp(
                    field.FIELDERS_HOME["1루수"], field.B1, rp)

        # 1루수가 직접 잡고 1루로 이동할 때 공 위치를 수비수와 동기화
        fb = plan.get("field_by")
        if (fb == "1루수" and self.anim_t > tf
                and plan.get("throw_to") == field.B1
                and self._has_throw and not self._dp_throw):
            self.ball_pos = self.fielder_positions["1루수"]
            self.ball_h = 4.0

    # ------------------------------------------------ 그리기
    def draw(self, s):
        g = self.game
        off_col = self._team_color(g.batting_team)
        def_col = self._team_color(g.defending_team)
        field.draw_field(s)
        self._draw_defense(s, def_col)
        field.draw_catcher(s, def_col)
        field.draw_umpire(s)
        field.draw_batter(s, right_handed=self.game.batter_is_right(),
                          swing=self.swing_progress or 0.0, jersey_color=off_col)

        if self.phase == P_BATTED:
            self._draw_runners(s)
            field.draw_ball(s, self.ball_pos, self.ball_h)
        elif self.phase in (P_READY, P_PITCH):
            self._draw_pitch_ball(s)

        self._draw_scoreboard(s)
        self._draw_status(s)
        if self.phase in (P_READY, P_PITCH):
            self._draw_pitch_info(s)
        if self.phase == P_PITCH and self._human_batting():
            self._draw_timing_meter(s)
        if not self._human_batting() and not g.one_player and self.phase in (P_READY, P_PITCH, P_BATTED):
            draw_text(s, "상대팀 공격 중...", 22, C.WIDTH // 2, C.HEIGHT - 22,
                      C.ACCENT2, center=True, bold=True)
        self.btn_menu.draw(s)

        if self.phase == P_SELECT:
            self._draw_pitch_select(s)
        if self.phase != P_RESULT:
            self._draw_count_panel(s)
        if self.phase == P_RESULT:
            self._draw_result_banner(s)
        if self.phase == P_INNING_CHANGE:
            self._draw_inning_change(s)
        if self.phase == P_ROUND_CLEAR:
            self._draw_round_clear(s)
        if self.paused:
            self._draw_pause_overlay(s)

    def _draw_defense(self, s, jersey_color):
        for name, pos in self.fielder_positions.items():
            gside = -1 if name in ("3루수", "유격수", "좌익수") else 1
            field.draw_fielder(s, pos, jersey_color, glove_side=gside)

    def _draw_runners(self, s):
        p = min(1.0, self.anim_t / max(0.3, self.anim_total - 0.15))
        for start, end, out, col, t0 in self.runner_tracks:
            pp = 0.0 if p <= t0 else (p - t0) / max(1e-3, 1.0 - t0)
            pos = _runner_pos(start, end, pp)
            c = C.GRAY if (out and p > 0.85) else col
            field.draw_runner(s, pos, c)

    def _draw_pitch_ball(self, s):
        t = 0.0 if self.phase == P_READY else min(self.t, 1.0)
        pos = _lerp(field.MOUND, field.HOME, t)
        h = 22.0 * (1.0 - t)
        field.draw_ball(s, pos, h)

    # ------------------------------------------------ 전광판(라인스코어)
    def _draw_scoreboard(self, s):
        if self.game.one_player:
            self._draw_solo_scoreboard(s)
            return
        g = self.game
        name_w, inn_w, tot_w = 108, 50, 46
        board_w = name_w + inn_w * 9 + tot_w * 4
        ox = (C.WIDTH - board_w) // 2
        oy = 8
        row_h = 28
        head_h = 24
        inner_h = head_h + row_h * 2 + 4
        frame_h = inner_h + 18

        # 전광판 프레임(실제 구장 스코어보드 느낌)
        frame = pygame.Rect(ox - 18, oy - 6, board_w + 36, frame_h)
        pygame.draw.rect(s, (48, 52, 62), frame, border_radius=10)
        pygame.draw.rect(s, (28, 32, 42), frame, width=3, border_radius=10)
        # 상단 조명 라인
        for lx in range(frame.left + 14, frame.right - 14, 18):
            pygame.draw.circle(s, (255, 236, 140), (lx, frame.top + 5), 3)
        # 좌우 지지대
        pygame.draw.rect(s, (58, 62, 72), (frame.left + 8, frame.bottom - 4, 10, 28))
        pygame.draw.rect(s, (58, 62, 72), (frame.right - 18, frame.bottom - 4, 10, 28))

        panel_y = oy + 10
        pygame.draw.rect(s, C.SCOREBOARD_BG, (ox - 6, panel_y, board_w + 12, inner_h),
                         border_radius=4)
        pygame.draw.rect(s, C.SCOREBOARD_LINE, (ox - 6, panel_y, board_w + 12, inner_h),
                         width=2, border_radius=4)

        # 헤더
        hy = panel_y + head_h // 2 + 2
        draw_text(s, "TEAM", 17, ox + name_w // 2, hy, C.LIGHT_GRAY, center=True, bold=True)
        for i in range(9):
            cx = ox + name_w + inn_w * i + inn_w // 2
            cur = (i + 1 == g.inning)
            draw_text(s, str(i + 1), 17, cx, hy,
                      C.ACCENT2 if cur else C.LIGHT_GRAY, center=True, bold=True)
        for j, lab in enumerate(("R", "H", "E", "B")):
            cx = ox + name_w + inn_w * 9 + tot_w * j + tot_w // 2
            draw_text(s, lab, 17, cx, hy, C.WHITE, center=True, bold=True)

        # 팀 두 줄
        for ti in range(2):
            ry = panel_y + head_h + row_h * ti
            attacking = (ti == g.batting_team)
            bg = (46, 66, 130) if attacking else C.SCOREBOARD_BG
            pygame.draw.rect(s, bg, (ox - 4, ry, board_w + 8, row_h))
            cy = ry + row_h // 2
            nm = g.team_names[ti]
            draw_text(s, nm, 19, ox + name_w // 2, cy,
                      C.ACCENT2 if attacking else C.WHITE, center=True, bold=True)
            for i in range(9):
                cx = ox + name_w + inn_w * i + inn_w // 2
                if i < len(g.line[ti]):
                    txt = str(g.line[ti][i])
                else:
                    txt = ""
                cur = attacking and (i + 1 == g.inning)
                draw_text(s, txt, 19, cx, cy,
                          C.ACCENT2 if cur else C.WHITE, center=True, bold=True)
            totals = (g.score[ti], g.hits[ti], g.errors[ti], g.walks[ti])
            for j, val in enumerate(totals):
                cx = ox + name_w + inn_w * 9 + tot_w * j + tot_w // 2
                col = C.FENCE_TOP if j == 0 else C.WHITE
                draw_text(s, str(val), 20, cx, cy, col, center=True, bold=True)

        gx = ox + name_w
        pygame.draw.line(s, C.SCOREBOARD_LINE, (gx, panel_y + head_h),
                         (gx, panel_y + inner_h - 2), 2)
        gx2 = ox + name_w + inn_w * 9
        pygame.draw.line(s, C.FENCE_TOP, (gx2, panel_y + 2),
                         (gx2, panel_y + inner_h - 2), 2)

    def _draw_solo_scoreboard(self, s):
        """1인 모드: 라운드·목표·누적 점수·아웃 전광판."""
        g = self.game
        w, h = 620, 78
        ox = (C.WIDTH - w) // 2
        oy = 8
        frame = pygame.Rect(ox - 14, oy - 4, w + 28, h + 16)
        pygame.draw.rect(s, (48, 52, 62), frame, border_radius=10)
        pygame.draw.rect(s, (28, 32, 42), frame, width=3, border_radius=10)
        for lx in range(frame.left + 16, frame.right - 16, 20):
            pygame.draw.circle(s, (255, 236, 140), (lx, frame.top + 5), 3)

        panel_y = oy + 8
        pygame.draw.rect(s, C.SCOREBOARD_BG, (ox, panel_y, w, h), border_radius=6)
        pygame.draw.rect(s, C.SCOREBOARD_LINE, (ox, panel_y, w, h), width=2,
                         border_radius=6)

        target = g.solo_target()
        pts = g.solo_points
        outs_left = g.solo_outs_left()
        outs_max = g.solo_outs_limit()

        draw_text(s, "타격 챌린지", 20, ox + 18, panel_y + 16, C.ACCENT2,
                  bold=True)
        draw_text(s, f"R{g.solo_round}", 22, ox + 150, panel_y + 16, C.WHITE,
                  center=True, bold=True)
        draw_text(s, f"목표 {target}점", 18, ox + 250, panel_y + 16,
                  C.LIGHT_GRAY, center=True)
        draw_text(s, f"아웃 {outs_left}/{outs_max}", 18,
                  ox + w - 18, panel_y + 16, C.ACCENT, right=True, bold=True)

        draw_text(s, f"{pts}", 40, ox + 90, panel_y + 58, C.FENCE_TOP,
                  center=True, bold=True)
        draw_text(s, "점", 18, ox + 140, panel_y + 60, C.LIGHT_GRAY)

        bar_x, bar_y, bar_w, bar_h = ox + 200, panel_y + 46, w - 230, 16
        pygame.draw.rect(s, (20, 28, 48), (bar_x, bar_y, bar_w, bar_h),
                         border_radius=8)
        round_start = g.solo_round_start_points
        span = max(1, target - round_start)
        prog = max(0.0, min(1.0, (pts - round_start) / span))
        fill_w = 0 if prog <= 0 else max(4, int(bar_w * prog))
        pygame.draw.rect(s, C.GOOD, (bar_x, bar_y, fill_w, bar_h), border_radius=8)
        pygame.draw.rect(s, C.WHITE, (bar_x, bar_y, bar_w, bar_h), width=1,
                         border_radius=8)
        draw_text(s, f"{pts}/{target}", 15, bar_x + bar_w // 2, bar_y + bar_h // 2,
                  C.WHITE, center=True, bold=True)

    # ------------------------------------------------ 상태(주자/아웃/타자)
    def _draw_status(self, s):
        g = self.game
        # 미니 베이스 + 이닝/아웃 (우측, 전광판 다리 아래)
        bx, by = C.WIDTH - 118, 168
        d = 12
        dia = {"1B": (bx + d, by), "2B": (bx, by - d), "3B": (bx - d, by)}
        for i, key in enumerate(("1B", "2B", "3B")):
            cx, cy = dia[key]
            on = g.bases[i]
            pts = [(cx, cy - 7), (cx + 7, cy), (cx, cy + 7), (cx - 7, cy)]
            pygame.draw.polygon(s, C.ACCENT2 if on else (70, 80, 70), pts)
            pygame.draw.polygon(s, C.WHITE, pts, 1)
        if g.one_player:
            draw_text(s, f"라운드 {g.solo_round}", 18, bx, by + 22, C.ACCENT2,
                      center=True, bold=True)
        else:
            draw_text(s, g.half_label(), 18, bx, by + 22, C.WHITE, center=True,
                      bold=True)
        if g.one_player:
            outs_max = g.solo_outs_limit()
            outs_left = g.solo_outs_left()
            draw_text(s, f"남은 아웃 {outs_left}/{outs_max}", 18, bx, by + 44,
                      C.LIGHT_GRAY, center=True)
        else:
            outs = "●" * g.outs + "○" * (C.OUTS_PER_INNING - g.outs)
            draw_text(s, f"아웃 {outs}", 18, bx, by + 44, C.LIGHT_GRAY, center=True)

        # 수비팀·타자 — 이닝/아웃 표시 아래(우측)
        name, order = g.current_batter_name()
        hand = "우타" if g.batter_is_right() else "좌타"
        ty = by + 68
        if not g.one_player:
            draw_text(s, f"수비: {g.team_names[g.defending_team]}", 16, bx, ty,
                      C.BLACK, center=True, bold=True)
            ty += 22
        draw_text(s, f"타석: {order}번 {name} ({hand})", 17, bx, ty,
                  C.BLACK, center=True, bold=True)
        if not g.one_player:
            ty += 20
            draw_text(s, g.current_batter_stats_compact(), 15, bx, ty,
                      C.BLACK, center=True)

    def _draw_pitch_info(self, s):
        pass  # 구종/구속은 _draw_count_panel 아래에 표시

    def _draw_timing_meter(self, s):
        bar_w, bar_h = 440, 18
        x = C.WIDTH // 2 - bar_w // 2
        y = C.HEIGHT - 26
        # 바탕
        pygame.draw.rect(s, (14, 16, 24), (x - 3, y - 3, bar_w + 6, bar_h + 6),
                         border_radius=8)
        # 구간 색칠 + HIT 라벨
        for a, b, _pmin, _pmax, color, label in GAUGE_ZONES:
            seg_x = x + int(a * bar_w)
            seg_w = max(1, int((b - a) * bar_w))
            pygame.draw.rect(s, color, (seg_x, y, seg_w, bar_h))
            if label:
                draw_text(s, label, 13, seg_x + seg_w // 2, y + bar_h // 2,
                          C.WHITE, center=True, bold=True)
        # 테두리
        pygame.draw.rect(s, C.WHITE, (x, y, bar_w, bar_h), width=2, border_radius=4)
        # 스윕 커서
        mx = x + int(min(self.t, 1.0) * bar_w)
        pygame.draw.polygon(s, C.WHITE,
                            [(mx, y - 6), (mx - 5, y - 13), (mx + 5, y - 13)])
        pygame.draw.line(s, C.WHITE, (mx, y - 4), (mx, y + bar_h + 4), 3)

    def _draw_pitch_select(self, s):
        """2인 수비: 좌측 구종 선택 패널."""
        g = self.game
        x, y, w, h = LEFT_PANEL_X, PITCH_PANEL_Y, 228, PITCH_PANEL_H
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((10, 14, 22, 215))
        s.blit(panel, (x, y))
        pygame.draw.rect(s, C.ACCENT2, (x, y, w, h), width=2, border_radius=8)
        draw_text(s, f"{g.team_names[g.defending_team]} 수비", 18, x + 12, y + 16,
                  C.WHITE, bold=True)
        draw_text(s, "구종을 선택하세요", 16, x + 12, y + 38, C.LIGHT_GRAY)
        if g.defending_team == 0:
            labels = ("[8] 패스트볼", "[9] 슬라이더", "[0] 커브")
        else:
            labels = ("[1] 패스트볼", "[2] 슬라이더", "[3] 커브")
        for i, lab in enumerate(labels):
            draw_text(s, lab, 16, x + 12, y + 62 + i * 26, C.LIGHT_GRAY)

    def _draw_count_panel(self, s):
        """S B O 카운트 현황판 (스트라이크=노랑, 볼=초록, 아웃=빨강)."""
        x, y, w, h = LEFT_PANEL_X, COUNT_PANEL_Y, 228, 58
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((10, 14, 22, 200))
        s.blit(panel, (x, y))
        pygame.draw.rect(s, (70, 80, 110), (x, y, w, h), width=2, border_radius=8)

        labels = (("S", C.ACCENT2), ("B", C.GOOD), ("O", C.ACCENT))
        if self.game.one_player:
            outs_max = self.game.solo_outs_limit()
            counts = (self.strikes, self.balls, self.game.solo_outs_used)
            maxes = (2, 3, outs_max)
        else:
            counts = (self.strikes, self.balls, self.game.outs)
            maxes = (2, 3, 3)
        slot_w = w // 3
        for i, ((lab, col), cnt, mx) in enumerate(zip(labels, counts, maxes)):
            cx = x + slot_w * i + slot_w // 2
            draw_text(s, lab, 18, cx, y + 14, col, center=True, bold=True)
            if self.game.one_player and i == 2:
                draw_text(s, f"{cnt}/{mx}", 18, cx, y + 40, col,
                          center=True, bold=True)
                continue
            span = (mx - 1) * 20
            for b in range(mx):
                bx = cx - span // 2 + b * 20
                lit = b < cnt
                bulb_col = col if lit else (38, 42, 52)
                pygame.draw.circle(s, bulb_col, (bx, y + 40), 7)
                if lit:
                    pygame.draw.circle(s, C.WHITE, (bx, y + 40), 7, 1)
                else:
                    pygame.draw.circle(s, (58, 62, 72), (bx, y + 40), 7, 1)

        if self.phase in (P_READY, P_PITCH, P_BATTED) and self.pitch_speed > 0:
            draw_text(s, f"{self.pitch_name}  {self.pitch_speed} km/h", 16,
                      x + 10, y + h + 18, C.BLACK, bold=True)

    def _draw_result_banner(self, s):
        lines = self.result_text.split("\n")
        gap = 8
        pad_x, pad_y = 36, 26
        rendered = []
        for i, line in enumerate(lines):
            score_sub = (line.startswith("+") or "타점 적시타" in line
                         or "득점" in line)
            size = 44 if i == 0 else (22 if score_sub else 24)
            col = self.result_color if i == 0 else (
                C.FENCE_TOP if score_sub else C.LIGHT_GRAY)
            font = get_font(size, bold=(i == 0))
            rendered.append((font.render(line, True, col), col))

        text_h = sum(img.get_height() for img, _ in rendered)
        text_h += gap * max(0, len(rendered) - 1)
        text_w = max(img.get_width() for img, _ in rendered)
        w = max(500, text_w + pad_x * 2)
        h = text_h + pad_y * 2
        rect = pygame.Rect(0, 0, w, h)
        rect.center = (C.WIDTH // 2, C.HEIGHT // 2)

        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((12, 14, 20, 225))
        s.blit(panel, rect.topleft)
        pygame.draw.rect(s, self.result_color, rect, width=4, border_radius=10)

        y = rect.top + (h - text_h) // 2
        for img, _col in rendered:
            x = rect.centerx - img.get_width() // 2
            s.blit(img, (x, y))
            y += img.get_height() + gap

    def _draw_pause_overlay(self, s):
        overlay = pygame.Surface((C.WIDTH, C.HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 165))
        s.blit(overlay, (0, 0))
        pw, ph = 360, 230
        px = (C.WIDTH - pw) // 2
        py = (C.HEIGHT - ph) // 2
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((18, 22, 32, 245))
        s.blit(panel, (px, py))
        pygame.draw.rect(s, C.ACCENT2, (px, py, pw, ph), width=3, border_radius=14)
        draw_text(s, "일시정지", 38, C.WIDTH // 2, py + 52, C.WHITE,
                  center=True, bold=True)
        draw_text(s, "게임이 잠시 멈췄습니다", 20, C.WIDTH // 2, py + 92,
                  C.LIGHT_GRAY, center=True)
        self.btn_resume.draw(s)
        self.btn_quit_game.draw(s)

    def _draw_inning_change(self, s):
        overlay = pygame.Surface((C.WIDTH, C.HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 130))
        s.blit(overlay, (0, 0))
        w, h = 420, 120
        rect = pygame.Rect(0, 0, w, h)
        rect.center = (C.WIDTH // 2, C.HEIGHT // 2)
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((12, 14, 20, 230))
        s.blit(panel, rect.topleft)
        pygame.draw.rect(s, C.ACCENT2, rect, width=4, border_radius=12)
        draw_text(s, "이닝교대", 46, rect.centerx, rect.centery - 18,
                  C.ACCENT2, center=True, bold=True)
        draw_text(s, self.game.half_label(), 24, rect.centerx, rect.centery + 28,
                  C.WHITE, center=True, bold=True)

    def _draw_round_clear(self, s):
        g = self.game
        overlay = pygame.Surface((C.WIDTH, C.HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        s.blit(overlay, (0, 0))
        w, h = 460, 150
        rect = pygame.Rect(0, 0, w, h)
        rect.center = (C.WIDTH // 2, C.HEIGHT // 2)
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((12, 14, 20, 235))
        s.blit(panel, rect.topleft)
        pygame.draw.rect(s, C.GOOD, rect, width=4, border_radius=12)
        draw_text(s, "라운드 클리어!", 44, rect.centerx, rect.centery - 36,
                  C.GOOD, center=True, bold=True)
        draw_text(s, f"라운드 {g.solo_round} 진출", 26, rect.centerx,
                  rect.centery + 4, C.WHITE, center=True, bold=True)
        draw_text(s, f"다음 목표 {g.solo_target()}점 · 아웃 {g.solo_outs_limit()}회",
                  20, rect.centerx, rect.centery + 44, C.ACCENT2, center=True)


# ============================================================ 게임 종료
class GameOverScene:
    def __init__(self, app, game: LiveGame):
        self.app = app
        self.game = game
        again_label = "다시하기" if game.one_player else "다시 하기"
        quit_label = "그만하기" if game.one_player else "메인 메뉴"
        self.btn_again = Button((C.WIDTH // 2 - 230, 560, 210, 60),
                                again_label, size=28, color=C.ACCENT, hover=C.GOOD)
        self.btn_menu = Button((C.WIDTH // 2 + 20, 560, 210, 60),
                               quit_label, size=28)

    def handle(self, events):
        mouse = pygame.mouse.get_pos()
        for b in (self.btn_again, self.btn_menu):
            b.update(mouse)
        for e in events:
            if self.btn_again.clicked(e):
                self.app.change_scene(LineupScene(self.app, self.game.one_player))
            elif self.btn_menu.clicked(e):
                self.app.change_scene(MenuScene(self.app))

    def update(self, dt):
        pass

    def draw(self, s):
        s.fill(C.DARK_PANEL)
        g = self.game
        if g.one_player:
            draw_text(s, "게임 오버", 56, C.WIDTH // 2, 72, C.WHITE,
                      center=True, bold=True)
            draw_text(s, "타격 챌린지 결과", 24, C.WIDTH // 2, 118,
                      C.LIGHT_GRAY, center=True)

            pw, ph = 440, 300
            px = (C.WIDTH - pw) // 2
            py = 155
            panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
            panel.fill((18, 24, 38, 240))
            s.blit(panel, (px, py))
            pygame.draw.rect(s, C.SCOREBOARD_LINE, (px, py, pw, ph),
                             width=3, border_radius=14)

            cleared = g.solo_rounds_cleared
            draw_text(s, "최종 점수", 22, px + pw // 2, py + 36,
                      C.LIGHT_GRAY, center=True)
            draw_text(s, f"{g.solo_points}점", 52, px + pw // 2, py + 82,
                      C.FENCE_TOP, center=True, bold=True)

            draw_text(s, "진행 기록", 22, px + pw // 2, py + 148,
                      C.LIGHT_GRAY, center=True)
            if cleared > 0:
                draw_text(s, f"{cleared}라운드 클리어", 26, px + pw // 2, py + 182,
                          C.GOOD, center=True, bold=True)
            draw_text(s, f"{g.solo_round}라운드에서 탈락", 24, px + pw // 2, py + 218,
                      C.ACCENT2, center=True, bold=True)
            draw_text(s, f"(목표 {g.solo_target()}점 · 아웃 소진)", 18,
                      px + pw // 2, py + 252, C.LIGHT_GRAY, center=True)
            draw_text(s, f"안타 {g.hits[1]}개", 20, px + pw // 2, py + 278,
                      C.LIGHT_GRAY, center=True)
        else:
            is_tie = g.game_tied or g.score[0] == g.score[1]
            draw_text(s, "경기 종료", 56, C.WIDTH // 2, 72, C.WHITE,
                      center=True, bold=True)
            draw_text(s, f"{g.team_names[0]}  {g.score[0]}  :  {g.score[1]}  {g.team_names[1]}",
                      40, C.WIDTH // 2, 130, C.ACCENT2, center=True, bold=True)

            if is_tie:
                pw, ph = 460, 100
                px = (C.WIDTH - pw) // 2
                py = 218
                panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
                panel.fill((18, 24, 38, 240))
                s.blit(panel, (px, py))
                pygame.draw.rect(s, C.ACCENT2, (px, py, pw, ph),
                                 width=3, border_radius=14)
                draw_text(s, "무승부", 60, px + pw // 2, py + ph // 2,
                          C.ACCENT2, center=True, bold=True)
                self._draw_final_line(s, 410)
            else:
                self._draw_final_line(s, 175)
                if g.walk_off and g.score[1] > g.score[0]:
                    msg = f"끝내기 승리!  {g.team_names[1]}"
                    col = C.GOOD
                elif g.score[0] > g.score[1]:
                    msg = f"{g.team_names[0]} 승리!"
                    col = C.GOOD
                else:
                    msg = f"{g.team_names[1]} 승리!"
                    col = C.GOOD
                draw_text(s, msg, 34, C.WIDTH // 2, 450,
                          col, center=True, bold=True)
                mvp = g.pick_mvp()
                if mvp:
                    draw_text(s, "BEST PLAYER", 22, C.WIDTH // 2, 492,
                              C.ACCENT2, center=True, bold=True)
                    draw_text(s, mvp["line"], 20, C.WIDTH // 2, 522,
                              C.WHITE, center=True, bold=True)
        for b in (self.btn_again, self.btn_menu):
            b.draw(s)

    def _draw_final_line(self, s, top):
        g = self.game
        name_w, inn_w, tot_w = 108, 46, 44
        board_w = name_w + inn_w * 9 + tot_w * 4
        ox = (C.WIDTH - board_w) // 2
        row_h = 30
        pygame.draw.rect(s, C.SCOREBOARD_BG, (ox - 6, top - 28, board_w + 12,
                                              28 + row_h * 2 + 6), border_radius=6)
        for i in range(9):
            cx = ox + name_w + inn_w * i + inn_w // 2
            draw_text(s, str(i + 1), 16, cx, top - 14, C.LIGHT_GRAY, center=True)
        for j, lab in enumerate(("R", "H", "E", "B")):
            cx = ox + name_w + inn_w * 9 + tot_w * j + tot_w // 2
            draw_text(s, lab, 16, cx, top - 14, C.WHITE, center=True, bold=True)
        for ti in range(2):
            cy = top + row_h * ti + row_h // 2
            draw_text(s, g.team_names[ti], 18, ox + name_w // 2, cy, C.WHITE,
                      center=True, bold=True)
            for i in range(9):
                cx = ox + name_w + inn_w * i + inn_w // 2
                txt = str(g.line[ti][i]) if i < len(g.line[ti]) else ""
                draw_text(s, txt, 18, cx, cy, C.WHITE, center=True)
            for j, val in enumerate((g.score[ti], g.hits[ti], g.errors[ti], g.walks[ti])):
                cx = ox + name_w + inn_w * 9 + tot_w * j + tot_w // 2
                draw_text(s, str(val), 18, cx, cy,
                          C.FENCE_TOP if j == 0 else C.WHITE, center=True, bold=True)


def main():
    App().run()
