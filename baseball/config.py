"""게임 전역 설정과 색상 상수."""

WIDTH, HEIGHT = 960, 720
FPS = 60
TITLE = "히팅카운트"
VERSION = "1.0.3"
DEVELOPER = "최정우"
DEVELOPER_EMAIL = "jwoochoi2001@naver.com"

# ------------------------------------------------------------------ 색상
SKY = (128, 197, 235)
SKY_TOP = (86, 165, 222)
# 화면 56% 아래 배경 (관중석·콘코스 톤)
SKY_SPLIT = 0.56
SKY_LOWER = (92, 112, 132)
SKY_LOWER_DEEP = (64, 80, 100)
GRASS = (63, 148, 66)
GRASS_DARK = (52, 128, 55)
GRASS_LIGHT = (80, 168, 82)
DIRT = (168, 116, 74)
DIRT_DARK = (140, 94, 58)
FENCE = (34, 64, 120)
FENCE_TOP = (250, 220, 60)
LINE = (238, 238, 238)

WHITE = (245, 245, 245)
BLACK = (24, 24, 28)
GRAY = (120, 120, 128)
LIGHT_GRAY = (196, 200, 208)
DARK_PANEL = (30, 34, 44)
PANEL = (44, 50, 64)
PANEL_LIGHT = (60, 68, 86)

ACCENT = (240, 84, 68)        # 빨강 (주 강조)
ACCENT2 = (255, 196, 60)      # 노랑
GOOD = (86, 200, 120)         # 초록
BLUE = (72, 140, 236)

# 팀 색상 (팀0=원정·빨강, 팀1=홈·네이비)
TEAM_HOME = (36, 72, 156)
TEAM_AWAY = (231, 76, 60)
TEAM_COLORS = (TEAM_AWAY, TEAM_HOME)

# ------------------------------------------------------------------ 게임 규칙
OUTS_PER_INNING = 3
MAX_INNINGS = 9          # 9회 한정, 연장 없음, 동점이면 무승부
DEFAULT_INNINGS = MAX_INNINGS
INNINGS = MAX_INNINGS

# ------------------------------------------------------------------ 탑다운 색상
CAP_GLOVE = (120, 78, 40)     # 글러브
JERSEY = (238, 238, 244)      # 수비 유니폼
UMP_COLOR = (40, 44, 54)      # 심판
INFIELD = (176, 122, 78)      # 내야 흙
INFIELD_DARK = (150, 100, 62)
MOUND_DIRT = (186, 134, 90)
SCOREBOARD_BG = (28, 46, 96)  # 전광판 남색
SCOREBOARD_LINE = (70, 96, 170)

# 관중석 / 담장 / 외야 전광판
STANDS = (58, 72, 108)        # 관중석 좌석(남색 톤)
STANDS_DARK = (42, 54, 82)
STANDS_RAIL = (78, 92, 128)
STANDS_SEAT = (48, 62, 96)
WALL = (26, 58, 44)           # 외야 담장(짙은 초록 패딩)
WALL_TOP = (250, 220, 60)     # 담장 상단 노란 라인
BOARD_BG = (16, 20, 28)       # 외야 전광판 본체
BOARD_ON = (96, 210, 130)     # 전광판 켜진 셀
BOARD_OFF = (34, 40, 52)      # 전광판 꺼진 셀

# 1인 모드 기본 타자
DEFAULT_1P_BATTER = "플레이어"
DEFAULT_1P_RIGHT = True  # 우타

# 2인 모드 기본 팀 이름 (원정·홈)
DEFAULT_TEAM_AWAY = "플레이어A"
DEFAULT_TEAM_HOME = "플레이어B"

# 1인 모드 (타격 챌린지) — 누적 점수·라운드별 아웃·목표
SOLO_OUTS_START = 10           # 1라운드 아웃
SOLO_OUTS_MIN = 5              # 최소 아웃 (6라운드 이후)
SOLO_OUTS_STEP = 1             # 라운드마다 아웃 1개 감소
SOLO_ROUND_BASE = 300          # 1라운드 목표 (누적)
SOLO_ROUND_GAP_START = 400     # 1→2 라운드 구간 (+400)
SOLO_ROUND_GAP_STEP = 100      # 라운드마다 구간 +100 (2→3 +500, 3→4 +600 …)
SOLO_HIT_POINTS = {1: 30, 2: 50, 3: 70, 4: 100}
SOLO_RUN_POINTS = 50

# 2인 모드 기본 라인업(1~9번). 사용자가 자유롭게 바꿀 수 있다.
DEFAULT_LINEUP = [f"플레이어{i}" for i in range(1, 10)]
# 좌타/우타 기본값 (True = 우타)
DEFAULT_RIGHT = [True] * 9

# 2인 모드 원정팀(AWAY) 기본 라인업·좌우타·선발투수
DEFAULT_LINEUP_AWAY = [f"플레이어{i}" for i in range(1, 10)]
DEFAULT_RIGHT_AWAY = [True] * 9
DEFAULT_PITCHER_AWAY = "플레이어10"
DEFAULT_PITCHER_RIGHT_AWAY = True  # 우투

# 2인 모드 홈팀(HOME) 기본 라인업·좌우타·선발투수
DEFAULT_LINEUP_HOME = [f"플레이어{i}" for i in range(1, 10)]
DEFAULT_RIGHT_HOME = [True] * 9
DEFAULT_PITCHER_HOME = "플레이어10"
DEFAULT_PITCHER_RIGHT_HOME = True  # 우투
