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
# 1인 모드 CPU 투구 구종 확률(패스트볼 위주, 나머지는 슬라이더/커브가 균등 분배)
SOLO_PITCH_WEIGHTS = {"패스트볼": 0.65, "슬라이더": 0.175, "커브": 0.175}
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
# 주자가 목표 루까지 뛰는 데 걸리는 총 시간(세그먼트 수 = 지나가는 베이스 칸 수).
# 세그먼트 수에 그냥 비례(1x,2x,3x,4x)시키면 3루타·홈런이 질질 끄는 느낌이라
# 루타별로 따로 정한다(1루타 1.8초 기준, 뒤로 갈수록 세그먼트당 증가폭은 줄어듦).
RUNNER_SEGMENT_TIME = {1: 1.8, 2: 2.8, 3: 3.6, 4: 4.3}
RUNNER_STEP_SEC = 1.8   # 위 표에 없는 경우(이론상 없음)의 기본 세그먼트당 시간
REL_THROW_DELAY = 0.5   # 외야수가 공을 잡은(t_flight) 후 중계 송구를 시작하기까지 지연
REL_THROW_LEG = 0.85    # 중계 송구 한 구간(외야수→중계수비수, 중계수비수→3루수) 시간
GAP_LEG1_FRAC = 0.55    # gap_pass_dist 정보가 없을 때(안전장치) 쓰는 기본 거리 비중
GAP_LEG1_SPEED = 230.0  # 내야수를 스쳐 지나가기 전까지 속도(ft/s, 직선타 아웃과 비슷)
GAP_LEG2_SPEED = 85.0   # 내야수를 지나 외야 쪽으로 흘러갈 때 속도(ft/s, 느려짐 — 외야수가 앞으로 달려나와 잡도록)
UMPIRE_STEP_SPEED = 16.0  # 심판이 수비수를 피할 때 실제로 걸어서 움직이는 속도(ft/s)

# 좌측 패널 위치(구종 선택 / S B O)
LEFT_PANEL_X = 14
PITCH_PANEL_Y = 112
PITCH_PANEL_W = 228
PITCH_PANEL_H = 190

# 투수 교체 팝업 크기
PITCHER_SUB_PW = 440
PITCHER_SUB_PH = 260
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
    ("body", "  플레이어A(원정·빨강) 수비: [1] 패스트볼 [2] 슬라이더 [3] 커브"),
    ("body", "  플레이어B(홈·파랑) 수비: [8] 패스트볼 [9] 슬라이더 [0] 커브"),
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
    ("body", "· 안타·2루타·3루타·홈런, 내야 안타, 실책"),
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
    ("body", "· 구종 선택(2인): A팀 1/2/3, B팀 8/9/0"),
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
LINEUP_ROW_H = 42
LINEUP_COL_W = 452
LINEUP_COL_X = (22, C.WIDTH - 22 - LINEUP_COL_W)
TEAM_LABELS = ("AWAY", "HOME")
TEAM_LABEL_COLORS = (C.TEAM_AWAY, C.TEAM_HOME)


class LineupScene:
    def __init__(self, app, one_player, prefill_game=None):
        self.app = app
        self.one_player = one_player
        self.inputs = []
        self.team_inputs = []
        self.hand_btns = []
        self.pitcher_inputs = []
        if one_player:
            # 1인: 타자 한 명만 설정 (직전 경기가 있으면 그 이름으로 미리 채운다)
            self._name_default = (prefill_game.lineups[1][0] if prefill_game
                                  else C.DEFAULT_1P_BATTER)
            self.names = [self._name_default]
            self.right = [prefill_game.right[1][0] if prefill_game
                         else C.DEFAULT_1P_RIGHT]
            cx = C.WIDTH // 2
            self.inputs.append(TextInput((cx - 160, 320, 320, 56),
                                         text=self.names[0], max_len=8))
            self.hand_btns.append(Button((cx - 80, 410, 160, 52),
                                         "우타" if self.right[0] else "좌타",
                                         size=26))
            self.btn_start = Button((C.WIDTH // 2 - 110, 640, 220, 60),
                                    "경기 시작", size=30, color=C.ACCENT,
                                    hover=C.GOOD)
            self.btn_back = Button((40, 640, 140, 54), "뒤로", size=24,
                                   color=C.PANEL, hover=C.GRAY)
        else:
            # 2인: 원정팀·홈팀 각각 팀 이름 + 1~9번 라인업 + 선발투수
            # (직전 경기가 있으면 그 라인업으로 미리 채운다)
            if prefill_game:
                self.names = [list(prefill_game.lineups[0]),
                              list(prefill_game.lineups[1])]
                self.right = [list(prefill_game.right[0]),
                             list(prefill_game.right[1])]
                self.pitcher_right = list(prefill_game.starting_pitcher_right)
                team_defaults = tuple(prefill_game.team_names)
                # 최종 등판 투수가 아니라 그 경기의 "선발" 투수 이름·투구 손으로 채운다
                pitcher_defaults = tuple(prefill_game.starting_pitchers)
            else:
                self.names = [list(C.DEFAULT_LINEUP_AWAY), list(C.DEFAULT_LINEUP_HOME)]
                self.right = [list(C.DEFAULT_RIGHT_AWAY), list(C.DEFAULT_RIGHT_HOME)]
                self.pitcher_right = [C.DEFAULT_PITCHER_RIGHT_AWAY,
                                      C.DEFAULT_PITCHER_RIGHT_HOME]
                team_defaults = (C.DEFAULT_TEAM_AWAY, C.DEFAULT_TEAM_HOME)
                pitcher_defaults = (C.DEFAULT_PITCHER_AWAY, C.DEFAULT_PITCHER_HOME)
            self._name_defaults = (list(self.names[0]), list(self.names[1]))
            self._team_defaults = team_defaults
            self._pitcher_defaults = pitcher_defaults
            self.inputs = [[], []]
            self.hand_btns = [[], []]
            self.pitcher_hand_btns = []
            self.lineup_top = 168
            for t in range(2):
                cx0 = LINEUP_COL_X[t]
                # 선수 이름 칸(가운데 = cx0+139)과 좌우 중앙이 맞도록 배치
                self.team_inputs.append(
                    TextInput((cx0 + 49, self.lineup_top - 54, 180, 40),
                              text=team_defaults[t], max_len=8))
                for i in range(9):
                    row_y = self.lineup_top + i * LINEUP_ROW_H
                    self.inputs[t].append(
                        TextInput((cx0 + 50, row_y, 178, 34),
                                 text=self.names[t][i], max_len=8))
                    self.hand_btns[t].append(
                        Button((cx0 + 238, row_y, 84, 34),
                              "우타" if self.right[t][i] else "좌타", size=17))
                pitcher_y = self.lineup_top + 9 * LINEUP_ROW_H + 8
                self.pitcher_inputs.append(
                    TextInput((cx0 + 50, pitcher_y, 178, 34),
                             text=pitcher_defaults[t], max_len=8))
                self.pitcher_hand_btns.append(
                    Button((cx0 + 238, pitcher_y, 84, 34),
                          "우투" if self.pitcher_right[t] else "좌투", size=17))
            btn_y = self.lineup_top + 10 * LINEUP_ROW_H + 32
            self.btn_start = Button((C.WIDTH // 2 - 110, btn_y, 220, 56),
                                    "경기 시작", size=26, color=C.ACCENT,
                                    hover=C.GOOD)
            self.btn_back = Button((40, btn_y + 2, 140, 52), "뒤로",
                                   size=22, color=C.PANEL, hover=C.GRAY)

    def _all_text_inputs(self):
        if self.one_player:
            return list(self.inputs)
        return (list(self.team_inputs) + self.inputs[0] + self.inputs[1]
                + self.pitcher_inputs)

    def _all_hand_buttons(self):
        if self.one_player:
            return list(self.hand_btns)
        return self.hand_btns[0] + self.hand_btns[1] + self.pitcher_hand_btns

    def handle(self, events):
        mouse = pygame.mouse.get_pos()
        for b in self._all_hand_buttons() + [self.btn_start, self.btn_back]:
            b.update(mouse)
        for e in events:
            for inp in self._all_text_inputs():
                inp.handle(e)
            if self.one_player:
                for i, b in enumerate(self.hand_btns):
                    if b.clicked(e):
                        self.right[i] = not self.right[i]
                        b.text = "우타" if self.right[i] else "좌타"
            else:
                for t in range(2):
                    for i, b in enumerate(self.hand_btns[t]):
                        if b.clicked(e):
                            self.right[t][i] = not self.right[t][i]
                            b.text = "우타" if self.right[t][i] else "좌타"
                    if self.pitcher_hand_btns[t].clicked(e):
                        self.pitcher_right[t] = not self.pitcher_right[t]
                        self.pitcher_hand_btns[t].text = (
                            "우투" if self.pitcher_right[t] else "좌투")
            if self.btn_back.clicked(e):
                self.app.change_scene(MenuScene(self.app))
            elif self.btn_start.clicked(e):
                self._start()

    def _start(self):
        if self.one_player:
            name = self.inputs[0].text.strip() or self._name_default
            lineups = [list(C.DEFAULT_LINEUP), [name]]
            team_names = ["상대팀", "우리팀"]
            rights = [list(C.DEFAULT_RIGHT), list(self.right)]
            pitchers = ["", ""]
        else:
            lineups = [
                [inp.text.strip() or self._name_defaults[t][i]
                 for i, inp in enumerate(self.inputs[t])]
                for t in range(2)
            ]
            team_names = [
                self.team_inputs[0].text.strip() or self._team_defaults[0],
                self.team_inputs[1].text.strip() or self._team_defaults[1],
            ]
            rights = [list(self.right[0]), list(self.right[1])]
            pitchers = [
                self.pitcher_inputs[0].text.strip() or self._pitcher_defaults[0],
                self.pitcher_inputs[1].text.strip() or self._pitcher_defaults[1],
            ]
        game = LiveGame(self.one_player, lineups, team_names)
        game.right = rights
        game.pitchers = pitchers
        game.starting_pitchers = list(pitchers)
        game.pitcher_right = (list(self.pitcher_right) if not self.one_player
                              else [True, True])
        game.starting_pitcher_right = list(game.pitcher_right)
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
            draw_text(s, "2인 게임 - 라인업 설정", 32, C.WIDTH // 2, 40,
                      C.WHITE, center=True, bold=True)
            for t in range(2):
                cx0 = LINEUP_COL_X[t]
                # 팀 이름은 선수 이름 칸(cx0+139)과 좌우 중앙을 맞춘다
                draw_text(s, TEAM_LABELS[t], 15, cx0 + 139,
                          self.lineup_top - 74, TEAM_LABEL_COLORS[t],
                          center=True, bold=True)
                self.team_inputs[t].draw(s)
                hdr_y = self.lineup_top - 10
                draw_text(s, "타순", 14, cx0 + 25, hdr_y, C.LIGHT_GRAY, center=True)
                draw_text(s, "이름", 14, cx0 + 139, hdr_y, C.LIGHT_GRAY, center=True)
                draw_text(s, "타격", 14, cx0 + 280, hdr_y, C.LIGHT_GRAY, center=True)
                for i in range(9):
                    row_y = self.lineup_top + i * LINEUP_ROW_H
                    draw_text(s, f"{i + 1}번", 18, cx0 + 25, row_y + 17,
                              C.ACCENT2, center=True, bold=True)
                    self.inputs[t][i].draw(s)
                    self.hand_btns[t][i].draw(s)
                pitcher_y = self.lineup_top + 9 * LINEUP_ROW_H + 8
                draw_text(s, "투수", 18, cx0 + 25, pitcher_y + 17,
                          C.GOOD, center=True, bold=True)
                self.pitcher_inputs[t].draw(s)
                self.pitcher_hand_btns[t].draw(s)
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
P_PITCHER_CHANGE = "pitcher_change"


def _lerp(a, b, p):
    return (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)


def _step_toward(cur, target, speed, dt):
    """cur 에서 target 방향으로 speed(ft/s)만큼만 이동(순간이동 방지)."""
    dx, dy = target[0] - cur[0], target[1] - cur[1]
    dist = math.hypot(dx, dy)
    step = speed * dt
    if dist <= step or dist < 1e-6:
        return target
    return (cur[0] + dx / dist * step, cur[1] + dy / dist * step)


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


_INFIELD_SHIFT_NAMES = ("1루수", "2루수", "유격수", "3루수")


def _infield_shift_target(name, landing):
    """2·3루타 중계 때 내야수가 타구 방향으로 살짝 붙는 목표 지점.

    외야수처럼 거리 비율로 움직이면(먼 타구일수록) 수십 피트씩 뛰어가는
    것처럼 보이므로, 내야수는 절대 거리로 3~14ft 정도만 자리를 잡는다.
    """
    hx, hy = field.FIELDERS_HOME[name]
    lx, ly = landing
    dx, dy = lx - hx, ly - hy
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return (hx, hy)
    ld = math.hypot(lx, ly)
    hd = math.hypot(hx, hy)
    alignment = 0.0
    if ld > 1e-6 and hd > 1e-6:
        alignment = (hx / hd) * (lx / ld) + (hy / hd) * (ly / ld)
    step = min(dist, 4.0 + 10.0 * max(0.0, alignment))
    return (hx + dx / dist * step, hy + dy / dist * step)


def _runner_pos(start_idx, end_idx, p):
    if end_idx == start_idx:
        return BASEPATH[start_idx]
    fp = start_idx + (end_idx - start_idx) * max(0.0, min(1.0, p))
    i0 = int(math.floor(fp))
    i1 = min(i0 + 1, 4)
    return _lerp(BASEPATH[i0], BASEPATH[i1], fp - i0)


def _runner_duration(segments):
    """주자가 segments 칸을 뛰는 데 걸리는 총 시간(루타별 표, 없으면 비례)."""
    segments = max(1, segments)
    return RUNNER_SEGMENT_TIME.get(segments, RUNNER_STEP_SEC * segments)


class PlayScene:
    def __init__(self, app, game: LiveGame):
        self.app = app
        self.game = game
        self.phase = None
        self.strikes = 0
        self.balls = 0
        self.timer = 0.0

        # 타석 표시용 캐시 — 결과가 확정되는 순간(apply_plan) 바로 다음
        # 타자로 게임 상태가 넘어가버려도, 화면에는 이번 타석 결과 애니메이션이
        # 다 끝날 때까지 방금 타석에 섰던 선수 정보를 계속 보여준다.
        name, order = game.current_batter_name()
        self._display_name = name
        self._display_order = order
        self._display_hand_right = game.batter_is_right()
        self._display_stats_lines = (
            game.current_batter_stats_lines() if not game.one_player else ("", ""))

        self.pitch_name = "패스트볼"
        self.pitch_speed = 0
        self.t = 0.0
        self.swung = False
        self.swing_progress = None
        self.plan = None

        # 타구 애니메이션 상태
        self.anim_t = 0.0
        self.anim_total = 0.0
        self.ball_resolve_t = 0.0
        self.t_flight = 1.0
        self.ball_pos = field.HOME
        self.ball_h = 0.0
        self.fielder_positions = dict(field.FIELDERS_HOME)
        self.runner_tracks = []   # (start_idx, end_idx, out, color)
        self._runner_free_pace = False
        self._of_relay = False
        self._of_relay_first = None
        self._of_relay_final = None
        self._gap_pass_frac = GAP_LEG1_FRAC
        self._gap_t1 = 0.0
        self._gap_mid = field.HOME
        self._ump_disp = {"1B": field.UMPIRE_1B, "2B": field.UMPIRE_2B,
                          "3B": field.UMPIRE_3B}

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

        # 투수 교체
        self.show_pitcher_sub = False
        self.pitcher_sub_input = None
        self.pitcher_sub_right = True
        self.pitcher_sub_hand_btn = None
        self.btn_pitcher_sub = Button(
            (LEFT_PANEL_X + PITCH_PANEL_W - 12 - 64, PITCH_PANEL_Y + 8, 64, 44),
            "교체", size=14, color=C.BLUE, hover=C.GOOD)
        pw, ph = PITCHER_SUB_PW, PITCHER_SUB_PH
        px, py = (C.WIDTH - pw) // 2, (C.HEIGHT - ph) // 2
        self.btn_pitcher_sub_confirm = Button(
            (px + 40, py + 180, 170, 54), "교체", size=24,
            color=C.GOOD, hover=C.ACCENT2)
        self.btn_pitcher_sub_cancel = Button(
            (px + 230, py + 180, 170, 54), "닫기", size=24,
            color=C.PANEL, hover=C.GRAY)

        self._begin_at_bat()

    # ------------------------------------------------ 흐름
    def _human_batting(self):
        """현재 타석을 사람이 조작하는가."""
        return not self.game.one_player or self.game.batting_team == 1

    def _pitch_keys(self):
        """2인 모드 수비 팀별 구종 선택 키 (A=8/9/0, B=1/2/3)."""
        if self.game.defending_team == 1:
            return PITCH_KEYS_A
        return PITCH_KEYS_B

    def _pitch_from_input(self, key=None, text=None):
        """KEYDOWN·TEXTINPUT 모두에서 구종 이름을 해석 (macOS 호환)."""
        if key is not None:
            keys = self._pitch_keys()
            if key in keys:
                return keys[key]
        if text:
            ch = text.lower() if self.game.defending_team == 1 else text
            letters = PITCH_LETTER_A if self.game.defending_team == 1 else PITCH_LETTER_B
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
        # 이전 타구(파울 등)의 애니메이션 상태가 다음 투구(삼진·볼넷)로
        # 새어 들어가 러너를 잘못 그리지 않도록 초기화.
        self.anim_t = 0.0
        self.anim_total = 0.0
        self._runner_free_pace = False
        self._of_relay = False
        self._gap_pass_frac = GAP_LEG1_FRAC
        self._gap_t1 = 0.0
        self._gap_mid = field.HOME
        # 이번에 타석에 들어서는 타자 정보로 표시 캐시 갱신(직전 타석 결과
        # 애니메이션이 끝나기 전엔 이 값이 아니라 이전 캐시가 화면에 남아있다).
        name, order = self.game.current_batter_name()
        self._display_name = name
        self._display_order = order
        self._display_hand_right = self.game.batter_is_right()
        if not self.game.one_player:
            self._display_stats_lines = self.game.current_batter_stats_lines()
        if self.game.is_over():
            self.app.change_scene(GameOverScene(self.app, self.game))
            return
        # 투수: 1인 모드는 항상 CPU 랜덤 구종, 2인은 수비 플레이어가 선택
        if self.game.one_player:
            names = list(SOLO_PITCH_WEIGHTS.keys())
            weights = list(SOLO_PITCH_WEIGHTS.values())
            self.pitch_name = random.choices(names, weights=weights, k=1)[0]
            self._roll_speed()
            self.phase = P_READY
            self.timer = 0.55
        else:
            self.phase = P_SELECT

    def _roll_speed(self):
        lo, hi = PITCHES[self.pitch_name]["speed"]
        self.pitch_speed = random.randint(lo, hi)

    # ------------------------------------------------ 투수 교체
    def _open_pitcher_sub(self):
        pw = PITCHER_SUB_PW
        px, py = (C.WIDTH - pw) // 2, (C.HEIGHT - PITCHER_SUB_PH) // 2
        # 현재 투수 정보로 미리 채우지 않고 항상 기본값(플레이어/우투)으로 연다.
        self.pitcher_sub_right = True
        self.pitcher_sub_input = TextInput((px + 40, py + 92, 220, 48),
                                           text="플레이어", max_len=8)
        self.pitcher_sub_hand_btn = Button(
            (px + 280, py + 92, 120, 48), "우투", size=20)
        self.show_pitcher_sub = True

    def _close_pitcher_sub(self, apply):
        self.show_pitcher_sub = False
        if apply:
            g = self.game
            team = g.defending_team
            name = self.pitcher_sub_input.text.strip()
            if name:
                g.pitchers[team] = name
            g.pitcher_right[team] = self.pitcher_sub_right
            self.phase = P_PITCHER_CHANGE
            self.timer = 1.6

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
            else:
                self._show_result("STRIKE OUT!", C.ACCENT)
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
            # 내야 직선타(liner)는 정면으로 총알같이 꽂히는 타구라 더 빨리 도달하지만,
            # 주자 뜀박질 속도까지 같이 빨라지진 않는다(아래 러너 페이스는 별도 고정).
            self.t_flight = {"ground": 1.0, "fly": 1.35, "liner": 0.6}.get(bt, 1.35)
            if bt == "fly" and plan["kind"] == "hr":
                self.t_flight = 1.7
            if bt == "gap":
                # 실제로 그 내야수 옆을 스쳐 지나가는 지점(gap_pass_dist)까지는
                # 빠르게, 그 이후 외야 쪽으로 흘러갈 때는 느려지도록 두 구간
                # 속도를 정해서 거리 기반으로 소요 시간을 계산한다.
                total_dist = field.dist_ft(field.HOME, plan["landing"])
                pass_dist = plan.get("gap_pass_dist", total_dist * GAP_LEG1_FRAC)
                pass_dist = min(pass_dist, total_dist * 0.9) if total_dist > 0 else 0.0
                self._gap_pass_frac = (pass_dist / total_dist) if total_dist > 0 else GAP_LEG1_FRAC
                self._gap_t1 = pass_dist / GAP_LEG1_SPEED
                gap_t2 = max(0.0, total_dist - pass_dist) / GAP_LEG2_SPEED
                self.t_flight = self._gap_t1 + gap_t2
                # 방향이 도중에 꺾이지 않도록(외야수 쪽으로 휘어 보이는 문제)
                # 처음 뻗어나간 방향 그대로 직진시킨다 — 옆으로 비켜가는 연출은
                # 하지 않는다.
                self._gap_mid = _lerp(field.HOME, plan["landing"], self._gap_pass_frac)
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
                # +0.55: 수비수 도착 페이스(tf+0.5)가 다 끝날 때까지는 애니메이션이
                # 유지되도록 여유를 준다(그보다 짧으면 수비수가 도착하기 전에
                # 다음 타석으로 넘어가 버린다).
                self.anim_total = self.t_flight + (0.7 if self._has_throw else 0.55)

        # 주자 트랙 구성.
        # - 송구(1루 송구/포스아웃/병살)가 있는 플레이는 주자가 "송구와 경합"하는
        #   장면이라 기존처럼 anim_total 에 맞춰(=송구 도착과 싱크) 뛰어야 한다.
        # - 캐치로 끝나는 아웃(뜬공·직선타·태그업)이나 안타는 경합 상대가 없으니
        #   타구 속도와 무관하게 루타별 고정 페이스로 뛴다.
        self._runner_free_pace = not (self._has_throw or self._dp_throw)
        self.runner_tracks = self._build_tracks(plan)
        if self.runner_tracks and self._runner_free_pace:
            needed = max(t0 + _runner_duration(abs(end - start))
                        for start, end, out, col, t0 in self.runner_tracks)
            self.anim_total = max(self.anim_total, needed + 0.15)

        # 2·3루타 연출용 중계 송구(결과에는 영향 없음) — 외야수가 공을 잡고
        # 가만히 서 있지 않도록, 잡은 뒤 근처 내야수(2루수/유격수)에게 공을
        # 준다. 베이스가 아니라 그 내야수의 실제 수비 위치가 목표 지점.
        self._of_relay = bool(plan.get("relay_fielder"))
        self._of_relay_first = plan.get("relay_fielder")
        self._of_relay_final = plan.get("relay_final")
        if self._of_relay:
            # 중계 송구가 끝까지(내야수가 공을 받을 때까지) 다 보이도록 그
            # 시점까지 애니메이션을 늘려둔다 — 안 그러면 송구 도중에 다음
            # 타석으로 넘어가 버린다.
            relay_legs = 2 if self._of_relay_final else 1
            relay_end = self.t_flight + REL_THROW_DELAY + REL_THROW_LEG * relay_legs
            self.anim_total = max(self.anim_total, relay_end + 0.2)

        # 판정(안타/아웃/홈런 등)이 확정되는 시점.
        # - 홈런·1루타·실책은 공이 담장을 넘거나 떨어지는 순간 이미 결과가
        #   정해지므로 t_flight 에 바로 멘트를 띄운다.
        # - 2루타·3루타는 타자주자가 실제로 그 베이스를 밟는 순간에 멘트를 띄운다.
        # - 캐치로 끝나는 아웃(뜬공·직선타·태그업)도 잡히는 순간 바로 멘트.
        # - 송구로 승부가 갈리는 아웃(포스아웃·병살 등)만 송구 도착까지 기다린다.
        # 어느 경우든 주자는 배너가 뜬 뒤에도 화면에서 계속 제 속도로 달린다.
        if plan["kind"] == "hit" and plan.get("bases", 1) in (2, 3):
            self.ball_resolve_t = _runner_duration(plan["bases"])
        elif plan["kind"] in ("hit", "hr") or (
                plan["kind"] != "foul" and self._runner_free_pace):
            # 실책(error)은 송구까지 포함된 플레이라 여기서 제외 — 송구가
            # 끝나야(anim_total) 비로소 "실책 출루"가 확정되는 그림이 자연스럽다.
            self.ball_resolve_t = self.t_flight
        else:
            self.ball_resolve_t = self.anim_total

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
                    tracks.append((3, 4, False, off, self.t_flight))   # 3루→홈
                if b[1]:
                    tracks.append((2, 3, False, off, self.t_flight))   # 2루→3루
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
        # 판정을 주자가 다 뛰기 전에 미리 낸 경우(자유 페이스), 배너가 주자보다
        # 먼저 사라지지 않도록 남은 주루 시간만큼 배너 표시 시간을 늘려둔다.
        runner_remaining = max(0.0, self.anim_total - self.anim_t)
        if self.game.is_over() and self.game.skipped_bottom_9th:
            self._show_result("경기 종료", C.ACCENT2, long_display=True)
            self.timer = max(self.timer, runner_remaining + 0.3)
            return
        if self.game.is_over() and self.game.game_tied:
            self._show_result("경기 종료\n무승부", C.ACCENT2, long_display=True)
            self.timer = max(self.timer, runner_remaining + 0.3)
            return
        text, col = self._play_result_message(self.plan)
        wo = self.game.walk_off
        scored = (self.game.solo_last_gain if self.game.one_player
                  else self.game.last_runs) > 0
        long_display = wo or self.plan["kind"] == "hr" or (
            scored and self.plan["kind"] == "out")
        self._show_result(text, col, long_display=long_display)
        self.timer = max(self.timer, runner_remaining + 0.3)

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

        if self.show_pitcher_sub:
            self.pitcher_sub_hand_btn.update(mouse)
            self.btn_pitcher_sub_confirm.update(mouse)
            self.btn_pitcher_sub_cancel.update(mouse)
            for e in events:
                self.pitcher_sub_input.handle(e)
                if self.pitcher_sub_hand_btn.clicked(e):
                    self.pitcher_sub_right = not self.pitcher_sub_right
                    self.pitcher_sub_hand_btn.text = (
                        "우투" if self.pitcher_sub_right else "좌투")
                elif self.btn_pitcher_sub_confirm.clicked(e):
                    self._close_pitcher_sub(apply=True)
                elif self.btn_pitcher_sub_cancel.clicked(e):
                    self._close_pitcher_sub(apply=False)
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    self._close_pitcher_sub(apply=False)
            return

        self.btn_menu.update(mouse)
        if self.phase == P_SELECT:
            self.btn_pitcher_sub.update(mouse)
        for e in events:
            if self.phase == P_SELECT and self.btn_pitcher_sub.clicked(e):
                self._open_pitcher_sub()
                return
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
        if self.paused or self.show_pitcher_sub:
            return

        if self.swing_progress is not None and self.swing_progress < 1.0:
            self.swing_progress = min(1.0, self.swing_progress + dt / SWING_ANIM_SEC)

        for key, home in (("1B", field.UMPIRE_1B), ("2B", field.UMPIRE_2B),
                          ("3B", field.UMPIRE_3B)):
            target = self._umpire_pos(home)
            self._ump_disp[key] = _step_toward(self._ump_disp[key], target,
                                               UMPIRE_STEP_SPEED, dt)

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
            if self.anim_t >= self.ball_resolve_t:
                self._finish_batted()
        elif self.phase == P_RESULT:
            # 판정은 이미 나왔지만(배너 표시 중) 주자가 아직 베이스를 다 안
            # 돌았으면, 배너를 띄운 채로 공/주자 애니메이션을 계속 진행한다.
            if self.anim_t < self.anim_total:
                self.anim_t += dt
                self._update_batted()
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
        elif self.phase == P_PITCHER_CHANGE:
            self.timer -= dt
            if self.timer <= 0:
                self.phase = P_SELECT

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
        elif plan["ball_type"] == "gap":
            # 1-2루간/3-유간/라인 안타: 실제로 그 내야수 옆을 스쳐 지나가는
            # 지점(gap_pass_dist)까지는 직선타 아웃과 비슷하게 빠르게, 내야수를
            # 지나고 나면(외야 쪽으로 흘러갈 때) 느려진다.
            mid = self._gap_mid
            t1 = self._gap_t1
            t2 = max(0.05, self.t_flight - t1)
            if self.anim_t <= t1:
                tp = self.anim_t / max(0.05, t1)
                self.ball_pos = _lerp(field.HOME, mid, tp)
            else:
                tp = min(1.0, (self.anim_t - t1) / t2)
                self.ball_pos = _lerp(mid, land, tp)
            self.ball_h = 4.0
        else:
            self.ball_pos = _lerp(field.HOME, land, p)
            if plan["ball_type"] == "foul":
                self.ball_h = 55.0 * math.sin(math.pi * p)
            elif plan["ball_type"] == "fly":
                self.ball_h = 120.0 * math.sin(math.pi * p) * (1.4 if plan["kind"] == "hr" else 1.0)
            else:
                self.ball_h = 4.0

        # 2·3루타 중계 송구(연출용) — 외야수가 공을 잡은 뒤(수비수 도착 페이스와
        # 맞춰) 베이스가 아니라 근처 내야수(2루수/유격수, 3루타는 3루수까지 한
        # 번 더)에게 공을 준다. 결과에는 영향 없이 그림만 그린다.
        if self._of_relay and self.anim_t > tf:
            # 중계 내야수도 실제로는(아래 내야수 반응 이동 로직 때문에) 정위치가
            # 아니라 타구 방향으로 살짝 이동한 지점에 서 있으므로, 송구 목표도
            # 정위치가 아니라 그 이동 지점으로 맞춰야 공이 몸을 뚫고 지나가지
            # 않는다.
            first_pt = _infield_shift_target(self._of_relay_first, land)
            leg = REL_THROW_LEG
            start = tf + REL_THROW_DELAY
            if self._of_relay_final:
                final_pt = _infield_shift_target(self._of_relay_final, land)
                t1_end = start + leg
                t2_end = t1_end + leg
                if self.anim_t <= start:
                    self.ball_pos = land
                    self.ball_h = 0.0
                elif self.anim_t <= t1_end:
                    tp = (self.anim_t - start) / leg
                    self.ball_pos = _lerp(land, first_pt, tp)
                    self.ball_h = 8.0 * math.sin(math.pi * tp)
                elif self.anim_t <= t2_end:
                    tp = (self.anim_t - t1_end) / leg
                    self.ball_pos = _lerp(first_pt, final_pt, tp)
                    self.ball_h = 8.0 * math.sin(math.pi * tp)
                else:
                    self.ball_pos = final_pt
                    self.ball_h = 0.0
            else:
                t_end = start + leg
                if self.anim_t <= start:
                    self.ball_pos = land
                    self.ball_h = 0.0
                elif self.anim_t <= t_end:
                    tp = (self.anim_t - start) / leg
                    self.ball_pos = _lerp(land, first_pt, tp)
                    self.ball_h = 8.0 * math.sin(math.pi * tp)
                else:
                    self.ball_pos = first_pt
                    self.ball_h = 0.0

        # 담당 수비수 이동
        fb = plan.get("field_by")
        if fb and fb in self.fielder_positions:
            home_pos = field.FIELDERS_HOME[fb]
            fb_target = land
            if plan["kind"] == "out":
                fp = min(1.0, p * 1.05)
            elif plan.get("ball_type") == "gap":
                # 1-2루간/3-유간/라인 안타: 공이 내야를 완전히 빠져나가기
                # 전까지는 담당 외야수가 미리 반응하지 않다가, 빠져나간 뒤에
                # 실제 낙구 지점(land)까지 움직인다. 1-2루간/3-유간은 낙구
                # 지점 자체가 정위치보다 얕게 나오도록(gamestate 쪽에서)
                # 조정되어 있어서 자연스럽게 전진하는 그림이 된다.
                delay = self._gap_t1
                span = max(0.3, (tf + 0.5) - delay)
                fp = min(1.0, max(0.0, self.anim_t - delay) / span)
            else:
                # 안타(특히 2·3루타)는 주자를 다 뛰게 하려고 anim_total 이
                # 길게 늘어나 있는데, 수비수가 여기 맞춰 움직이면 공 떨어진
                # 곳까지 일부러 느릿느릿 가는 것처럼 보인다. 수비수는 공이
                # 떨어진 직후(t_flight + 짧은 여유) 안에 도착하도록 별도 페이스로.
                fp = min(1.0, self.anim_t / max(0.3, tf + 0.5))
            self.fielder_positions[fb] = _lerp(home_pos, fb_target, fp)
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

        # 2·3루타 중계 상황: 내야수들도 가만히 있지 않고 타구 방향으로
        # 외야수보다 훨씬 작은 폭으로 반응해 움직인다.
        if self._of_relay:
            infield_shift_p = min(1.0, p * 1.12)
            for name in _INFIELD_SHIFT_NAMES:
                if name == fb:
                    continue
                home = field.FIELDERS_HOME[name]
                target = _infield_shift_target(name, land)
                self.fielder_positions[name] = _lerp(home, target, infield_shift_p)

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
        field.draw_umpire(s, self._ump_disp["1B"])
        field.draw_umpire(s, self._ump_disp["2B"])
        field.draw_umpire(s, self._ump_disp["3B"])
        field.draw_batter(s, right_handed=self._display_hand_right,
                          swing=self.swing_progress or 0.0, jersey_color=off_col)

        if self.phase == P_BATTED or (
                self.phase == P_RESULT and self.anim_t < self.anim_total):
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
        if self.phase == P_PITCHER_CHANGE:
            self._draw_pitcher_change(s)
        if self.paused:
            self._draw_pause_overlay(s)
        if self.show_pitcher_sub:
            self._draw_pitcher_sub_modal(s)

    def _umpire_pos(self, home_pos, min_dist=20.0):
        """수비수가 다가오면(수비 애니메이션 중) 심판이 살짝 비켜서게 한다."""
        px, py = home_pos
        for fx, fy in self.fielder_positions.values():
            dx, dy = px - fx, py - fy
            dist = math.hypot(dx, dy)
            if 1e-3 < dist < min_dist:
                push = min_dist - dist
                px += dx / dist * push
                py += dy / dist * push
        return (px, py)

    def _draw_defense(self, s, jersey_color):
        for name, pos in self.fielder_positions.items():
            gside = -1 if name in ("3루수", "유격수", "좌익수") else 1
            field.draw_fielder(s, pos, jersey_color, glove_side=gside)

    def _draw_runners(self, s):
        if self._runner_free_pace:
            # 경합 상대(송구)가 없는 플레이: 루타별 고정 페이스로 달린다 —
            # 타구(공)가 빨리 잡히더라도 사람이 뛰는 속도는 항상 동일하다.
            for start, end, out, col, t0 in self.runner_tracks:
                dur = _runner_duration(abs(end - start))
                pp = 0.0 if self.anim_t <= t0 else min(1.0, (self.anim_t - t0) / dur)
                pos = _runner_pos(start, end, pp)
                c = C.GRAY if (out and pp > 0.85) else col
                field.draw_runner(s, pos, c)
        else:
            # 송구가 있는 플레이: 주자가 송구와 경합하는 느낌이 나야 한다.
            # - 세이프(내야안타 등): 기존처럼 송구 도착과 같은 시점(또는 살짝
            #   먼저) 베이스에 닿아야 "송구보다 빨랐다"는 그림이 된다.
            # - 아웃: 반대로 송구보다 살짝 늦게 도착해야 "송구에 걸려
            #   아웃됐다"는 판정이 납득된다. 그래서 아웃 주자만 head-start(0.15)
            #   없이(=송구가 도착하는 순간보다 뒤에) 도착하게 만든다.
            p_safe = min(1.0, self.anim_t / max(0.3, self.anim_total - 0.15))
            p_out = min(1.0, self.anim_t / max(0.3, self.anim_total))
            for start, end, out, col, t0 in self.runner_tracks:
                p = p_out if out else p_safe
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

        draw_text(s, "타격 챌린지", 20, ox + 18, panel_y + 6, C.ACCENT2,
                  bold=True)
        draw_text(s, f"R{g.solo_round}", 22, ox + 150, panel_y + 16, C.WHITE,
                  center=True, bold=True)
        draw_text(s, f"목표 {target}점", 18, ox + 250, panel_y + 16,
                  C.LIGHT_GRAY, center=True)
        draw_text(s, f"아웃 {outs_left}/{outs_max}", 18,
                  ox + w - 18, panel_y + 16, C.ACCENT, right=True, bold=True)

        draw_text(s, f"{pts}", 34, ox + 70, panel_y + 58, C.FENCE_TOP,
                  center=True, bold=True)
        draw_text(s, "점", 18, ox + 140, panel_y + 58, C.LIGHT_GRAY, center=True)

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
        if not g.one_player:
            outs = "●" * g.outs + "○" * (C.OUTS_PER_INNING - g.outs)
            draw_text(s, f"아웃 {outs}", 18, bx, by + 44, C.LIGHT_GRAY, center=True)

        # 타자 — 이닝/아웃 표시 아래(우측). 결과 애니메이션이 끝나기 전엔
        # 게임 상태가 이미 다음 타자로 넘어가 있어도, 화면은 이번에 실제로
        # 타석에 섰던 선수 정보(캐시)를 계속 보여준다.
        name, order = self._display_name, self._display_order
        hand = "우타" if self._display_hand_right else "좌타"
        ty = by + 68
        batter_label = f"{name} ({hand})" if g.one_player else f"{order}번 {name} ({hand})"
        draw_text(s, f"타석: {batter_label}", 17, bx, ty,
                  C.BLACK, center=True, bold=True)
        if not g.one_player:
            line1, line2 = self._display_stats_lines
            ty += 20
            draw_text(s, line1, 15, bx, ty, C.BLACK, center=True)
            ty += 18
            draw_text(s, line2, 15, bx, ty, C.BLACK, center=True)

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
        x, y, w, h = LEFT_PANEL_X, PITCH_PANEL_Y, PITCH_PANEL_W, PITCH_PANEL_H
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((10, 14, 22, 215))
        s.blit(panel, (x, y))
        pygame.draw.rect(s, C.ACCENT2, (x, y, w, h), width=2, border_radius=8)
        draw_text(s, f"공격: {g.team_names[g.batting_team]}", 16, x + 12, y + 14,
                  C.WHITE, bold=True)
        draw_text(s, f"수비: {g.team_names[g.defending_team]}", 16, x + 12, y + 34,
                  C.WHITE, bold=True)
        pitcher = g.pitchers[g.defending_team]
        if pitcher:
            hand = "우투" if g.pitcher_right[g.defending_team] else "좌투"
            draw_text(s, f"투수: {pitcher} ({hand})", 15, x + 12, y + 58,
                      C.ACCENT2)
        self.btn_pitcher_sub.draw(s)
        draw_text(s, "구종을 선택하세요", 16, x + 12, y + 82, C.LIGHT_GRAY)
        if g.defending_team == 1:
            labels = ("[8] 패스트볼", "[9] 슬라이더", "[0] 커브")
        else:
            labels = ("[1] 패스트볼", "[2] 슬라이더", "[3] 커브")
        for i, lab in enumerate(labels):
            draw_text(s, lab, 16, x + 12, y + 106 + i * 26, C.LIGHT_GRAY)

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

    def _draw_pitcher_sub_modal(self, s):
        overlay = pygame.Surface((C.WIDTH, C.HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 165))
        s.blit(overlay, (0, 0))
        pw, ph = PITCHER_SUB_PW, PITCHER_SUB_PH
        px = (C.WIDTH - pw) // 2
        py = (C.HEIGHT - ph) // 2
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((18, 22, 32, 245))
        s.blit(panel, (px, py))
        pygame.draw.rect(s, C.ACCENT2, (px, py, pw, ph), width=3, border_radius=14)
        draw_text(s, "투수 교체", 32, px + pw // 2, py + 40, C.WHITE,
                  center=True, bold=True)
        self.pitcher_sub_input.draw(s)
        self.pitcher_sub_hand_btn.draw(s)
        self.btn_pitcher_sub_confirm.draw(s)
        self.btn_pitcher_sub_cancel.draw(s)

    def _draw_pitcher_change(self, s):
        g = self.game
        overlay = pygame.Surface((C.WIDTH, C.HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 130))
        s.blit(overlay, (0, 0))
        w, h = 420, 120
        rect = pygame.Rect(0, 0, w, h)
        rect.center = (C.WIDTH // 2, C.HEIGHT // 2)
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((12, 14, 20, 230))
        s.blit(panel, rect.topleft)
        pygame.draw.rect(s, C.BLUE, rect, width=4, border_radius=12)
        draw_text(s, "투수교체", 46, rect.centerx, rect.centery - 18,
                  C.BLUE, center=True, bold=True)
        team = g.defending_team
        hand = "우투" if g.pitcher_right[team] else "좌투"
        draw_text(s, f"{g.pitchers[team]} ({hand})", 24,
                  rect.centerx, rect.centery + 28, C.WHITE, center=True, bold=True)

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
        # 2인 모드는 "기록" 버튼이 전광판 바로 아래, 다시하기/메뉴 버튼 위에 오도록
        # 버튼 행 자체를 조금 아래로 내린다.
        btn_row_y = 560 if game.one_player else 616
        # "다시하기" = 방금 경기한 라인업을 그대로 채운 라인업 설정 화면으로 이동
        self.btn_replay = Button((C.WIDTH // 2 - 230, btn_row_y, 210, 60),
                                 again_label, size=28)
        self.btn_menu = Button((C.WIDTH // 2 + 20, btn_row_y, 210, 60),
                               quit_label, size=28)
        self.show_stats = False
        self.btn_stats = None
        if not game.one_player:
            self.btn_stats = Button((C.WIDTH // 2 - 105, btn_row_y - 60, 210, 46),
                                    "기록", size=22, color=C.GOOD,
                                    hover=C.ACCENT)
        self.btn_stats_close = Button((C.WIDTH // 2 - 90, C.HEIGHT - 58, 180, 44),
                                      "닫기", size=24, color=C.PANEL, hover=C.GRAY)

    def handle(self, events):
        mouse = pygame.mouse.get_pos()
        if self.show_stats:
            self.btn_stats_close.update(mouse)
            for e in events:
                if self.btn_stats_close.clicked(e):
                    self.show_stats = False
            return
        buttons = [self.btn_replay, self.btn_menu]
        if self.btn_stats:
            buttons.append(self.btn_stats)
        for b in buttons:
            b.update(mouse)
        for e in events:
            if self.btn_replay.clicked(e):
                self._restart_same_lineup()
            elif self.btn_menu.clicked(e):
                self.app.change_scene(MenuScene(self.app))
            elif self.btn_stats and self.btn_stats.clicked(e):
                self.show_stats = True

    def _restart_same_lineup(self):
        self.app.change_scene(LineupScene(self.app, self.game.one_player,
                                          prefill_game=self.game))

    def update(self, dt):
        pass

    def draw(self, s):
        if self.show_stats:
            self._draw_boxscore(s)
            return
        s.fill(C.DARK_PANEL)
        g = self.game
        if g.one_player:
            draw_text(s, "게임 오버", 56, C.WIDTH // 2, 72, C.WHITE,
                      center=True, bold=True)

            pw, ph = 440, 300
            px = (C.WIDTH - pw) // 2
            py = 155
            panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
            panel.fill((18, 24, 38, 240))
            s.blit(panel, (px, py))
            pygame.draw.rect(s, C.SCOREBOARD_LINE, (px, py, pw, ph),
                             width=3, border_radius=14)

            draw_text(s, "최종 점수", 22, px + pw // 2, py + 36,
                      C.LIGHT_GRAY, center=True)
            draw_text(s, f"{g.solo_points}점", 52, px + pw // 2, py + 82,
                      C.FENCE_TOP, center=True, bold=True)

            draw_text(s, "진행 기록", 22, px + pw // 2, py + 148,
                      C.LIGHT_GRAY, center=True)
            draw_text(s, f"{g.solo_round}라운드 아웃", 24, px + pw // 2, py + 186,
                      C.ACCENT2, center=True, bold=True)
            draw_text(s, f"안타 {g.hits[1]}개", 20, px + pw // 2, py + 222,
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
                self._draw_final_line(s, 230)
                mvp = g.pick_mvp()
                if mvp:
                    draw_text(s, "BEST PLAYER", 22, C.WIDTH // 2, 360,
                              C.ACCENT2, center=True, bold=True)
                    draw_text(s, mvp["line"], 20, C.WIDTH // 2, 390,
                              C.WHITE, center=True, bold=True)
        for b in (self.btn_replay, self.btn_menu):
            b.draw(s)
        if self.btn_stats:
            self.btn_stats.draw(s)

    def _draw_boxscore(self, s):
        """양팀 타자 기록표(타수·안타·타점·홈런·볼넷·삼진·타율)."""
        g = self.game
        s.fill(C.DARK_PANEL)
        draw_text(s, "타자 기록", 40, C.WIDTH // 2, 44, C.WHITE,
                  center=True, bold=True)

        col_w = (38, 82, 38, 38, 38, 38, 38, 38, 56)
        headers = ("타순", "이름", "타수", "안타", "타점", "홈런", "볼넷", "삼진", "타율")
        table_w = sum(col_w)
        gap = 36
        total_w = table_w * 2 + gap
        start_x = (C.WIDTH - total_w) // 2
        top_y = 92
        row_h = 27

        for ti in range(2):
            tx = start_x + ti * (table_w + gap)
            draw_text(s, g.team_names[ti], 22, tx + table_w // 2, top_y,
                      C.WHITE, center=True, bold=True)
            hy = top_y + 32
            cx = tx
            for w, h in zip(col_w, headers):
                draw_text(s, h, 15, cx + w // 2, hy, C.LIGHT_GRAY,
                          center=True, bold=True)
                cx += w
            pygame.draw.line(s, C.GRAY, (tx, hy + 13), (tx + table_w, hy + 13), 1)

            for slot in range(9):
                ry = hy + 22 + slot * row_h
                st = g.batter_stats[ti][slot]
                name = g.lineups[ti][slot % len(g.lineups[ti])]
                if st["ab"] > 0:
                    avg = st["h"] / st["ab"]
                    avg_str = f"{avg:.3f}".lstrip("0") if avg < 1 else f"{avg:.3f}"
                else:
                    avg_str = "-"
                vals = (f"{slot + 1}", name, st["ab"], st["h"], st["rbi"],
                        st["hr"], st["bb"], st["k"], avg_str)
                cx = tx
                for w, val in zip(col_w, vals):
                    draw_text(s, str(val), 15, cx + w // 2, ry, C.WHITE,
                              center=True)
                    cx += w

        self.btn_stats_close.draw(s)

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
