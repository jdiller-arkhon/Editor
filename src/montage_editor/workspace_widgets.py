"""Code-native studio artwork and a timeline drawn only from real project data."""
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QLinearGradient, QRadialGradient, QFont
from PySide6.QtWidgets import QWidget


class CinemaCanvas(QWidget):
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w,h=self.width(),self.height()
        background=QLinearGradient(0,0,w,h)
        background.setColorAt(0,QColor('#171b24')); background.setColorAt(.5,QColor('#080a0f')); background.setColorAt(1,QColor('#171510'))
        p.fillRect(self.rect(),background)
        glow=QRadialGradient(w*.5,h*.28,w*.45)
        glow.setColorAt(0,QColor(216,193,145,45));glow.setColorAt(.5,QColor(139,152,180,12));glow.setColorAt(1,QColor(0,0,0,0))
        p.fillRect(self.rect(),glow)
        p.setPen(QPen(QColor(195,184,160,22),1))
        for size in [72,120,190,275]:
            p.drawEllipse(QRectF(w/2-size/2,h*.28-size/2,size,size))
        p.setPen(QPen(QColor(230,218,192,180),2))
        x,y=w/2,h*.28
        p.drawLine(int(x),int(y-26),int(x),int(y+26))
        p.drawLine(int(x-17),int(y-10),int(x+17),int(y-10))
        p.setPen(QColor('#545962'))
        for x,y,dx,dy in [(18,18,1,1),(w-18,18,-1,1),(18,h-18,1,-1),(w-18,h-18,-1,-1)]:
            p.drawLine(x,y,x+dx*15,y);p.drawLine(x,y,x,y+dy*15)
        p.setFont(QFont('Segoe UI',9));p.setPen(QColor('#6d737f'))
        p.drawText(QRectF(25,h-33,w-50,20),Qt.AlignLeft,'LOCAL STUDIO   /   NO MEDIA LOADED')


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
        p.fillRect(self.rect(),QColor('#0c0e13'))
        left=95; width=max(1,self.width()-110)
        total=sum(c.duration for c in self.timeline.clips) if self.timeline else 30
        p.setFont(QFont('Segoe UI',8))
        for i in range(7):
            x=left+width*i/6
            p.setPen(QColor('#222730'));p.drawLine(int(x),23,int(x),self.height()-10)
            p.setPen(QColor('#737b88'));p.drawText(QRectF(x,0,60,20),f'{total*i/6:.1f}s')
        for i,name in enumerate(['V1  FOOTAGE','A1  MUSIC','A2  DIALOGUE']):
            y=30+i*39
            p.setPen(QColor('#949aa5'));p.drawText(QRectF(8,y+8,86,20),name)
            p.fillRect(QRectF(left,y,width,30),QColor('#141821'))
        if not self.timeline:
            p.setPen(QColor('#616a79'))
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
            block(cursor,clip.duration,0,f'{index+1:02d}  {Path(clip.source).name}','#596579','#293344');cursor+=clip.duration
        block(0,total,1,Path(self.timeline.music).name,'#6d6651','#383427')
        for cue in self.timeline.dialogue:
            block(cue.at,cue.duration,2,cue.reference or Path(cue.source).name,'#536960','#293e35')
        x=left+width*max(0,min(total,self.position))/total
        p.setPen(QPen(QColor('#f1e2c0'),2));p.drawLine(int(x),20,int(x),self.height()-5)


class CathedralBanner(QWidget):
    def __init__(self):
        super().__init__()
        from PySide6.QtGui import QPixmap
        self.art=QPixmap(str(Path(__file__).parent/'resources'/'cathedral.jpg'))
        self.setMinimumHeight(170);self.setMaximumHeight(220)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        if not self.art.isNull():
            scaled=self.art.scaled(self.size(),Qt.KeepAspectRatioByExpanding,Qt.SmoothTransformation)
            p.drawPixmap((self.width()-scaled.width())//2,0,scaled)
        else:p.fillRect(self.rect(),QColor('#101216'))
        shade=QLinearGradient(0,0,0,self.height());shade.setColorAt(0,QColor(0,0,0,10));shade.setColorAt(1,QColor(0,0,0,110))
        p.fillRect(self.rect(),shade)
        p.setPen(QColor('#eeeeee'));font=QFont('Georgia',22);font.setLetterSpacing(QFont.AbsoluteSpacing,6);p.setFont(font)
        y=self.height()*.5
        p.drawText(QRectF(30,y,self.width()*.4,42),Qt.AlignCenter,'CREATE')
        p.drawText(QRectF(self.width()*.58,y,self.width()*.4-30,42),Qt.AlignCenter,'WITH PURPOSE')
        font=QFont('Segoe UI',9);font.setLetterSpacing(QFont.AbsoluteSpacing,4);p.setFont(font);p.setPen(QColor('#bfc1c4'))
        p.drawText(QRectF(0,self.height()-38,self.width(),25),Qt.AlignCenter,'FAITH  /  FOCUS  /  DISCIPLINE')
