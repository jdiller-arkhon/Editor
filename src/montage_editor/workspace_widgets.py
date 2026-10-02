"""Code-native studio artwork and a timeline drawn only from real project data."""
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QLinearGradient, QRadialGradient, QFont, QPainterPath
from PySide6.QtWidgets import QWidget


class CinemaCanvas(QWidget):
    """Abstract viewfinder, not footage or a religious title card."""
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w,h=self.width(),self.height()
        background=QLinearGradient(0,0,w,h)
        background.setColorAt(0,QColor('#202023'));background.setColorAt(.5,QColor('#111114'));background.setColorAt(1,QColor('#19191d'))
        p.fillRect(self.rect(),background)
        glow=QRadialGradient(w*.5,h*.24,w*.42)
        glow.setColorAt(0,QColor(225,225,240,25));glow.setColorAt(1,QColor(0,0,0,0))
        p.fillRect(self.rect(),glow)
        x,y=w/2,h*.25
        p.save();p.translate(x,y)
        for angle,offset in [(-8,-9),(5,7),(0,0)]:
            p.save();p.rotate(angle)
            rect=QRectF(-47+offset,-27+offset,94,54)
            p.setBrush(QColor(14,14,18,180));p.setPen(QPen(QColor(190,190,210,50),1))
            p.drawRoundedRect(rect,8,8);p.restore()
        play=QPainterPath();play.moveTo(-6,-10);play.lineTo(10,0);play.lineTo(-6,10);play.closeSubpath()
        p.setPen(Qt.NoPen);p.setBrush(QColor('#b8b8c4'));p.drawPath(play);p.restore()
        p.setPen(QColor('#4c4c56'))
        for x,y,dx,dy in [(18,18,1,1),(w-18,18,-1,1),(18,h-18,1,-1),(w-18,h-18,-1,-1)]:
            p.drawLine(x,y,x+dx*15,y);p.drawLine(x,y,x,y+dy*15)
        p.setFont(QFont('Segoe UI',8));p.setPen(QColor('#74747e'))
        p.drawText(QRectF(25,h-31,w-50,20),Qt.AlignLeft,'SCREENING ROOM  /  READY WHEN YOU ARE')


class TimelineLanes(QWidget):
    seek = Signal(float)

    def __init__(self):
        super().__init__();self.timeline=None;self.position=0
        self.setMinimumHeight(155);self.setMouseTracking(True)
        self.setToolTip('Video, music and dialogue from the saved timeline. Click to seek the rendered export.')

    def set_timeline(self,timeline):
        self.timeline=timeline;self.update()

    def set_position(self,seconds):
        self.position=seconds;self.update()

    def mousePressEvent(self,event):
        if self.timeline and self.width()>110:
            total=sum(c.duration for c in self.timeline.clips)
            fraction=max(0,min(1,(event.position().x()-95)/(self.width()-110)))
            self.seek.emit(fraction*total)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor('#101012'))
        left=95; width=max(1,self.width()-110)
        total=sum(c.duration for c in self.timeline.clips) if self.timeline else 30
        p.setFont(QFont('Segoe UI',8))
        for i in range(7):
            x=left+width*i/6
            p.setPen(QColor('#28282e'));p.drawLine(int(x),23,int(x),self.height()-10)
            p.setPen(QColor('#81818b'));p.drawText(QRectF(x,0,60,20),f'{total*i/6:.1f}s')
        for i,name in enumerate(['V1  FOOTAGE','A1  MUSIC','A2  DIALOGUE']):
            y=30+i*39
            p.setPen(QColor('#ababba'));p.drawText(QRectF(8,y+8,86,20),name)
            p.fillRect(QRectF(left,y,width,30),QColor('#1b1b20'))
        if not self.timeline:
            p.setPen(QColor('#777783'))
            p.drawText(QRectF(left+12,38,width-24,20),'Generate or open a timeline to reveal your edit')
            return
        def block(start,length,row,text,top,bottom):
            rect=QRectF(left+width*start/total,30+row*39,max(2,width*length/total-2),30)
            gradient=QLinearGradient(rect.topLeft(),rect.bottomLeft())
            gradient.setColorAt(0,QColor(top));gradient.setColorAt(1,QColor(bottom))
            p.setBrush(gradient);p.setPen(QColor(top));p.drawRoundedRect(rect,4,4)
            p.save();p.setClipRect(rect.adjusted(5,0,-3,0));p.setPen(QColor('#ededee'))
            p.drawText(rect.adjusted(7,5,0,0),text);p.restore()
        cursor=0
        for index,clip in enumerate(self.timeline.clips):
            block(cursor,clip.duration,0,f'{index+1:02d}  {Path(clip.source).name}','#646471','#363640');cursor+=clip.duration
        block(0,total,1,Path(self.timeline.music).name,'#68686f','#34343b')
        for cue in self.timeline.dialogue:
            block(cue.at,cue.duration,2,cue.reference or Path(cue.source).name,'#62626c','#33333d')
        x=left+width*max(0,min(total,self.position))/total
        p.setPen(QPen(QColor('#ededf6'),2));p.drawLine(int(x),20,int(x),self.height()-5)


class CathedralBanner(QWidget):
    """Purpose-led studio banner; architecture is a quiet background reference."""
    def __init__(self):
        super().__init__()
        from PySide6.QtGui import QPixmap
        self.art=QPixmap(str(Path(__file__).parent/'resources'/'cathedral.jpg'))
        self.setMinimumHeight(150);self.setMaximumHeight(175)
        self.setAccessibleName('DRIFT cinematic studio banner')

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        w,h=self.width(),self.height()
        p.setPen(Qt.NoPen)
        gradient=QLinearGradient(0,0,w,h)
        gradient.setColorAt(0,QColor('#242427'));gradient.setColorAt(.6,QColor('#16161a'));gradient.setColorAt(1,QColor('#0b0b0e'))
        p.setBrush(gradient);p.drawRoundedRect(QRectF(0,0,w,h),14,14)
        p.save();clip=QPainterPath();clip.addRoundedRect(QRectF(1,1,w-2,h-2),14,14);p.setClipPath(clip)
        if not self.art.isNull():
            scaled=self.art.scaled(self.size(),Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation)
            p.setOpacity(.07);p.drawPixmap((w-scaled.width())//2,(h-scaled.height())//2,scaled);p.setOpacity(1)
        glow=QRadialGradient(w*.82,h*.4,w*.4)
        glow.setColorAt(0,QColor(220,220,240,24));glow.setColorAt(1,QColor(0,0,0,0));p.fillRect(self.rect(),glow)
        p.save();p.translate(w*.78,h*.49)
        for angle,dx,dy in [(-12,-38,-3),(8,38,8),(0,0,0)]:
            p.save();p.translate(dx,dy);p.rotate(angle)
            p.setPen(Qt.NoPen);p.setBrush(QColor(0,0,0,65));p.drawRoundedRect(QRectF(-109,-38,224,96),10,10)
            face=QLinearGradient(-110,-48,110,48);face.setColorAt(0,QColor('#43434b'));face.setColorAt(1,QColor('#1a1a20'))
            p.setBrush(face);p.setPen(QPen(QColor(178,178,200,70),1));p.drawRoundedRect(QRectF(-112,-48,224,96),9,9)
            p.setPen(QPen(QColor(235,235,245,45),1));p.drawLine(-96,-32,96,-32);p.drawLine(-96,30,96,30)
            p.setFont(QFont('Segoe UI',9));p.setPen(QColor('#9999a8'));p.drawText(QRectF(-94,-19,188,38),Qt.AlignCenter,'D R I F T   /   STUDIO')
            p.restore()
        p.restore();p.restore()
        p.setBrush(Qt.NoBrush);p.setPen(QPen(QColor('#414149'),1));p.drawRoundedRect(QRectF(.5,.5,w-1,h-1),14,14)
        p.setFont(QFont('Segoe UI',8,QFont.DemiBold));p.setPen(QColor('#b5b5c0'))
        p.drawText(QRectF(30,20,w*.56,20),'THE MOMENT. THE MUSIC. THE STORY.')
        p.setFont(QFont('Segoe UI',26 if w>1000 else 22,QFont.DemiBold));p.setPen(QColor('#f0f0f4'))
        p.drawText(QRectF(28,50,w*.6,45),'Make every moment count.')
        p.setFont(QFont('Segoe UI',10));p.setPen(QColor('#b0b0bb'))
        p.drawText(QRectF(30,110,w*.6,23),'Your footage. Your soundtrack. A little more purpose.')
