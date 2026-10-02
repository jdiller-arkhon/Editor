"""Code-native studio artwork and a timeline drawn only from real project data."""
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QLinearGradient, QRadialGradient, QFont, QPainterPath
from PySide6.QtWidgets import QWidget

VIOLET, PINK, TEAL, AMBER, INK, MUTED = '#6d4dff', '#ff4f8b', '#11b3a3', '#ffad1f', '#15131f', '#6b6880'
DISPLAY, TEXT = 'Sora', 'Manrope'


def accent(x1, y1, x2, y2):
    gradient = QLinearGradient(x1, y1, x2, y2)
    gradient.setColorAt(0, QColor(VIOLET)); gradient.setColorAt(1, QColor(PINK))
    return gradient


def wash(p, x, y, radius, color, alpha):
    glow = QRadialGradient(x, y, radius)
    tint = QColor(color); tint.setAlpha(alpha)
    clear = QColor(color); clear.setAlpha(0)
    glow.setColorAt(0, tint); glow.setColorAt(1, clear)
    p.fillRect(QRectF(x-radius, y-radius, 2*radius, 2*radius), glow)


class BrandMark(QWidget):
    """Gradient tile with a play glyph; the app's only logo mark."""
    def __init__(self):
        super().__init__(); self.setFixedSize(30, 30)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen); p.setBrush(accent(0, 0, 30, 30)); p.drawRoundedRect(QRectF(0, 0, 30, 30), 9, 9)
        play = QPainterPath(); play.moveTo(12, 9); play.lineTo(21, 15); play.lineTo(12, 21); play.closeSubpath()
        p.setBrush(QColor('#ffffff')); p.drawPath(play)


class CinemaCanvas(QWidget):
    """Abstract viewfinder, not footage or a religious title card."""
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        clip = QPainterPath(); clip.addRoundedRect(QRectF(0, 0, w, h), 14, 14); p.setClipPath(clip)
        p.fillRect(self.rect(), QColor('#f6f4fd'))
        wash(p, w*.22, h*.15, w*.45, VIOLET, 46)
        wash(p, w*.85, h*.9, w*.4, PINK, 40)
        wash(p, w*.6, h*.1, w*.25, TEAL, 22)
        p.save(); p.translate(w/2, h*.3)
        for angle, offset, color in [(-9, -10, VIOLET), (6, 8, PINK), (0, 0, None)]:
            p.save(); p.rotate(angle)
            rect = QRectF(-50+offset, -29+offset, 100, 58)
            if color:
                tint = QColor(color); tint.setAlpha(40)
                p.setBrush(tint); p.setPen(Qt.NoPen)
            else:
                p.setBrush(QColor(255, 255, 255, 245)); p.setPen(QPen(QColor(109, 77, 255, 60), 1))
            p.drawRoundedRect(rect, 10, 10); p.restore()
        play = QPainterPath(); play.moveTo(-7, -11); play.lineTo(11, 0); play.lineTo(-7, 11); play.closeSubpath()
        p.setPen(Qt.NoPen); p.setBrush(accent(-7, -11, 11, 11)); p.drawPath(play); p.restore()


class TimelineLanes(QWidget):
    seek = Signal(float)
    LANES = (('FOOTAGE', VIOLET, '#8f75ff'), ('MUSIC', TEAL, '#3fcfc1'), ('DIALOGUE', AMBER, '#ffc65c'))

    def __init__(self):
        super().__init__(); self.timeline = None; self.position = 0
        self.setMinimumHeight(165); self.setMouseTracking(True)
        self.setToolTip('Video, music and dialogue from the saved timeline. Click to seek the rendered export.')

    def set_timeline(self, timeline):
        self.timeline = timeline; self.update()

    def set_position(self, seconds):
        self.position = seconds; self.update()

    def mousePressEvent(self, event):
        if self.timeline and self.width() > 110:
            total = sum(c.duration for c in self.timeline.clips)
            fraction = max(0, min(1, (event.position().x()-95)/(self.width()-110)))
            self.seek.emit(fraction*total)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor('#ffffff'))
        left = 95; width = max(1, self.width()-110)
        total = sum(c.duration for c in self.timeline.clips) if self.timeline else 30
        p.setFont(QFont(TEXT, 8))
        for i in range(7):
            x = left+width*i/6
            p.setPen(QColor('#f0eef6')); p.drawLine(int(x), 23, int(x), self.height()-10)
            p.setPen(QColor('#9a96b0')); p.drawText(QRectF(x-30 if i == 6 else x, 0, 60, 20),
                                                    Qt.AlignRight if i == 6 else Qt.AlignLeft, f'{total*i/6:.1f}s')
        for i, (name, color, _) in enumerate(self.LANES):
            y = 30+i*41
            p.setPen(Qt.NoPen); p.setBrush(QColor(color)); p.drawEllipse(QRectF(8, y+11, 8, 8))
            p.setFont(QFont(TEXT, 8, QFont.Bold)); p.setPen(QColor(MUTED)); p.drawText(QRectF(22, y+7, 74, 20), name)
            tint = QColor(color); tint.setAlpha(18)
            p.setPen(Qt.NoPen); p.setBrush(tint); p.drawRoundedRect(QRectF(left, y, width, 32), 7, 7)
        p.setFont(QFont(TEXT, 8))
        if not self.timeline:
            p.setPen(QColor('#8c88a3'))
            p.drawText(QRectF(left+12, 38, width-24, 20), 'Create or open a timeline to see your edit here')
            return

        def block(start, length, row, text):
            _, top, bottom = self.LANES[row]
            rect = QRectF(left+width*start/total, 30+row*41, max(2, width*length/total-2), 32)
            gradient = QLinearGradient(rect.topLeft(), rect.topRight())
            gradient.setColorAt(0, QColor(top)); gradient.setColorAt(1, QColor(bottom))
            p.setBrush(gradient); p.setPen(Qt.NoPen); p.drawRoundedRect(rect, 7, 7)
            p.save(); p.setClipRect(rect.adjusted(6, 0, -3, 0)); p.setPen(QColor('#ffffff'))
            p.drawText(rect.adjusted(8, 8, 0, 0), text); p.restore()
        cursor = 0
        for index, clip in enumerate(self.timeline.clips):
            block(cursor, clip.duration, 0, f'{index+1:02d}  {Path(clip.source).name}'); cursor += clip.duration
        block(0, total, 1, Path(self.timeline.music).name)
        for cue in self.timeline.dialogue:
            block(cue.at, cue.duration, 2, cue.reference or Path(cue.source).name)
        x = left+width*max(0, min(total, self.position))/total
        p.setPen(QPen(QColor(PINK), 2)); p.drawLine(int(x), 20, int(x), self.height()-5)
        p.setPen(Qt.NoPen); p.setBrush(QColor(PINK)); p.drawEllipse(QRectF(x-4, 16, 8, 8))


class CathedralBanner(QWidget):
    """Hero banner; the original architecture art stays a faint background texture."""
    def __init__(self):
        super().__init__()
        from PySide6.QtGui import QPixmap
        self.art = QPixmap(str(Path(__file__).parent/'resources'/'cathedral.jpg'))
        self.setMinimumHeight(170); self.setMaximumHeight(190)
        self.setAccessibleName('DRIFT studio banner')

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        clip = QPainterPath(); clip.addRoundedRect(QRectF(0, 0, w, h), 18, 18)
        p.setClipPath(clip)
        p.fillRect(self.rect(), QColor('#ffffff'))
        wash(p, w*.92, h*.1, w*.32, PINK, 70)
        wash(p, w*.7, h*1.0, w*.3, VIOLET, 70)
        wash(p, w*.52, h*.0, w*.18, TEAL, 40)
        wash(p, w*.05, h*1.1, w*.25, AMBER, 30)
        if not self.art.isNull():
            scaled = self.art.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.setOpacity(.04); p.drawPixmap((w-scaled.width())//2, (h-scaled.height())//2, scaled); p.setOpacity(1)
        p.save(); p.translate(w*.8, h*.52)
        for angle, dx, dy, alpha in [(-12, -46, -2, 70), (9, 46, 8, 70), (0, 0, 0, 255)]:
            p.save(); p.translate(dx, dy); p.rotate(angle)
            rect = QRectF(-100, -44, 200, 88)
            if alpha < 255:
                gradient = accent(-100, -44, 100, 44)
                p.setOpacity(alpha/255); p.setBrush(gradient); p.setPen(Qt.NoPen)
                p.drawRoundedRect(rect, 12, 12); p.setOpacity(1)
            else:
                p.setBrush(QColor(255, 255, 255, 240)); p.setPen(QPen(QColor(109, 77, 255, 70), 1))
                p.drawRoundedRect(rect, 12, 12)
                for i, color in enumerate((VIOLET, TEAL, AMBER)):
                    tint = QColor(color); tint.setAlpha(200)
                    p.setPen(Qt.NoPen); p.setBrush(tint)
                    p.drawRoundedRect(QRectF(-80, -24+i*18, [120, 150, 70][i], 10), 5, 5)
            p.restore()
        p.restore()
        p.setClipping(False)
        p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor('#ecebf3'), 1)); p.drawRoundedRect(QRectF(.5, .5, w-1, h-1), 18, 18)
        p.setFont(QFont(TEXT, 8, QFont.Bold)); p.setPen(QColor(VIOLET))
        p.drawText(QRectF(32, 26, w*.56, 20), 'THE MOMENT  •  THE MUSIC  •  THE STORY')
        p.setFont(QFont(DISPLAY, 28 if w > 1000 else 23, QFont.Bold))
        p.setPen(QColor(INK)); p.drawText(QRectF(30, 54, w*.62, 50), 'Make every moment ')
        offset = p.fontMetrics().horizontalAdvance('Make every moment ')
        p.setPen(QPen(accent(30+offset, 0, 30+offset+p.fontMetrics().horizontalAdvance('count.'), 0), 1))
        p.drawText(QRectF(30+offset, 54, w*.4, 50), 'count.')
        p.setFont(QFont(TEXT, 11)); p.setPen(QColor(MUTED))
        p.drawText(QRectF(32, 116, w*.6, 24), 'Your footage. Your soundtrack. A little more purpose.')
