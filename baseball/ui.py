"""버튼, 텍스트 입력 등 간단한 UI 위젯."""
import pygame

from . import config as C
from .assets import get_font


def draw_text(surface, text, size, x, y, color=C.WHITE, center=False,
              bold=False, right=False):
    """텍스트를 그리고 사용된 rect 를 돌려준다."""
    font = get_font(size, bold=bold)
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = (x, y)
    elif right:
        rect.midright = (x, y)
    else:
        rect.topleft = (x, y)
    surface.blit(img, rect)
    return rect


class Button:
    def __init__(self, rect, text, size=30, color=C.PANEL_LIGHT,
                 text_color=C.WHITE, hover=C.ACCENT):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.size = size
        self.color = color
        self.text_color = text_color
        self.hover = hover
        self.enabled = True
        self._hovered = False

    def draw(self, surface):
        base = self.color
        if not self.enabled:
            base = C.GRAY
        elif self._hovered:
            base = self.hover
        pygame.draw.rect(surface, base, self.rect, border_radius=12)
        pygame.draw.rect(surface, C.BLACK, self.rect, width=2, border_radius=12)
        draw_text(surface, self.text, self.size, self.rect.centerx,
                  self.rect.centery, self.text_color, center=True, bold=True)

    def update(self, mouse_pos):
        self._hovered = self.enabled and self.rect.collidepoint(mouse_pos)

    def clicked(self, event):
        if not self.enabled:
            return False
        return (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and self.rect.collidepoint(event.pos))


class TextInput:
    """클릭하면 활성화되고 키보드로 텍스트를 편집하는 입력창."""

    def __init__(self, rect, text="", size=26, max_len=8):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.size = size
        self.max_len = max_len
        self.active = False

    def handle(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                self.active = False
            elif event.unicode and len(self.text) < self.max_len:
                if event.unicode.isprintable():
                    self.text += event.unicode

    def draw(self, surface):
        border = C.ACCENT2 if self.active else C.BLACK
        pygame.draw.rect(surface, C.WHITE, self.rect, border_radius=8)
        pygame.draw.rect(surface, border, self.rect, width=3, border_radius=8)
        draw_text(surface, self.text, self.size, self.rect.centerx,
                  self.rect.centery, C.BLACK, center=True)
