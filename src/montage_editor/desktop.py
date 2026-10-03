"""Desktop workspace connected to the real local montage engine."""
import json
import threading
import numpy as np
from pathlib import Path
import sys
from datetime import datetime
from uuid import uuid4

from PySide6.QtCore import Qt, QThread, QTimer, Signal, QUrl, QSettings, QStandardPaths
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QApplication, QMainWindow, QTextBrowser, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QFileDialog, QListWidget, QFormLayout, QSpinBox, QDoubleSpinBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QProgressBar,
    QMessageBox, QSlider, QFrame, QStackedWidget, QGraphicsDropShadowEffect, QLineEdit, QScrollArea, QInputDialog)

from . import jobs
from .workspace_widgets import BrandMark, CinemaCanvas, TimelineLanes, CathedralBanner
from .music_library import find_songs, search_libraries, interpret_song, default_library, AUDIO, VIDEO
from .config import Settings, draft_of, preset, with_pace
from .vision_director import LOCAL_MODEL
from .pipeline import Timeline, create_montage, render, probe, analyze_gameplay, exchange_shots, retarget, swap_shots

STORY_TONES = {
    'subtle': ('Subtle • hope & perseverance', 'Keep the faith.',
               'Cinematic Christian undertone, expressed subtly through hope, humility and perseverance. Use restrained transitions and purposeful pacing.'),
    'christian': ('Christian • explicit message', 'Walk with Christ.',
                  'Cinematic Christian hope and perseverance. Express humility and following Christ; do not equate in-game kills with divine approval.'),
    'neutral': ('Neutral • gameplay focus', '',
                'Cinematic gameplay montage with a deliberate energy arc, restrained transitions and musical pacing.'),
}

# Palette: white canvas, ink text, violet→pink primary accent, teal (music) and amber (dialogue).
INK, MUTED, LINE = '#15131f', '#6b6880', '#e9e7f2'
VIOLET, PINK, TEAL, AMBER = '#6d4dff', '#ff4f8b', '#11b3a3', '#ffad1f'

CANCELLED = 'Cancelled'

STYLE = '''
QWidget {background:#ffffff;color:#15131f;font-family:Manrope,Segoe UI,sans-serif;font-size:13px;}
QMainWindow,QWidget#canvas {background:#f7f6fb;}
QFrame#appbar {background:#ffffff;border-bottom:1px solid #ecebf3;}
QFrame#panel {background:#ffffff;border:1px solid #ecebf3;border-radius:18px;}
QFrame#create {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ffffff,stop:.55 #fbf9ff,stop:1 #fff4f8);border:1px solid #e7e1ff;border-radius:18px;}
QFrame#dropzone {background:#faf8ff;border:1.5px dashed #c9bdff;border-radius:14px;}
QLabel {background:transparent;}
QWidget#step {background:transparent;}
QLabel#brand {font-family:Sora;font-size:19px;font-weight:800;letter-spacing:2px;color:#15131f;}
QLabel#title {font-family:Sora;font-size:18px;font-weight:700;color:#15131f;}
QLabel#section {font-family:Sora;font-size:15px;font-weight:700;color:#15131f;}
QLabel#muted {color:#6b6880;}
QLabel#eyebrow {color:#8c88a3;font-size:10px;font-weight:700;letter-spacing:2px;}
QLabel#badge {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #6d4dff,stop:1 #ff4f8b);color:#ffffff;font-family:Sora;font-weight:700;font-size:11px;border-radius:11px;min-width:22px;max-width:22px;min-height:22px;max-height:22px;qproperty-alignment:AlignCenter;}
QLabel#chip {background:#f1edff;color:#5a3df0;border-radius:11px;padding:4px 10px;font-size:11px;font-weight:700;}
QLabel#chipTeal {background:#e4f7f5;color:#0b8a7e;border-radius:11px;padding:4px 10px;font-size:11px;font-weight:700;}
QLabel#chipAmber {background:#fff4dc;color:#a76a00;border-radius:11px;padding:4px 10px;font-size:11px;font-weight:700;}
QLabel#chipPink {background:#ffe8f0;color:#d02a64;border-radius:11px;padding:4px 10px;font-size:11px;font-weight:700;}
QLabel#status {background:#f1edff;color:#4a33c9;border-radius:10px;padding:9px 12px;font-weight:600;}
QPushButton {background:#ffffff;border:1px solid #dedbea;border-radius:10px;padding:9px 14px;color:#15131f;font-weight:600;}
QPushButton:hover {background:#f6f3ff;border-color:#b9a9ff;color:#4a33c9;}
QPushButton:pressed {background:#ece6ff;}
QPushButton:focus {border:1px solid #6d4dff;}
QPushButton:disabled {color:#b5b2c4;background:#fbfbfd;border-color:#efeef4;}
QPushButton#primary {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6d4dff,stop:1 #ff4f8b);color:#ffffff;font-family:Sora;font-size:14px;font-weight:700;border:0;border-radius:12px;padding:14px 26px;}
QPushButton#primary:hover {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5d3df2,stop:1 #f23f7c);color:#ffffff;}
QPushButton#primary:pressed {background:#5a3df0;}
QPushButton#primary:disabled {background:#d9d4f3;color:#ffffff;}
QPushButton#nav {background:transparent;border:0;border-radius:10px;padding:8px 13px;color:#6b6880;font-weight:600;}
QPushButton#nav:hover {background:#f4f1ff;color:#4a33c9;}
QPushButton#nav:checked {background:#efeaff;color:#4a33c9;}
QListWidget,QTableWidget {background:#ffffff;border:1px solid #ecebf3;border-radius:10px;alternate-background-color:#faf9fd;selection-background-color:#efeaff;selection-color:#2d1f8f;gridline-color:#f1f0f6;}
QHeaderView::section {background:#faf9fd;color:#6b6880;border:0;border-bottom:1px solid #ecebf3;padding:7px;font-weight:700;}
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox {background:#ffffff;border:1px solid #dedbea;border-radius:10px;padding:9px;selection-background-color:#ddd3ff;selection-color:#15131f;}
QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus {border:1px solid #6d4dff;}
QComboBox::drop-down {border:0;width:26px;}
QComboBox::down-arrow {image:url(CHEVRON);width:10px;height:6px;}
QComboBox QAbstractItemView {background:#ffffff;border:1px solid #dedbea;selection-background-color:#efeaff;selection-color:#2d1f8f;}
QCheckBox {background:transparent;padding:4px 0;}
QCheckBox::indicator:checked {background:#6d4dff;border:1px solid #6d4dff;border-radius:4px;}
QProgressBar {border:0;background:#eeebf7;border-radius:3px;height:5px;}
QProgressBar::chunk {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6d4dff,stop:1 #ff4f8b);border-radius:3px;}
QSlider::groove:horizontal {height:4px;background:#e8e5f3;border-radius:2px;}
QSlider::sub-page:horizontal {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #6d4dff,stop:1 #ff4f8b);border-radius:2px;}
QSlider::handle:horizontal {background:#ffffff;border:2px solid #6d4dff;width:10px;margin:-5px 0;border-radius:7px;}
QSplitter::handle {background:#f7f6fb;width:12px;height:12px;}
QScrollArea {border:0;background:transparent;}
QScrollBar:vertical {background:transparent;width:8px;margin:0;}
QScrollBar::handle:vertical {background:#d9d5ea;border-radius:4px;min-height:24px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QToolTip {background:#15131f;color:#ffffff;border:0;padding:6px;}
QTextBrowser#chatlog {background:#faf9fd;border:1px solid #ecebf3;border-radius:12px;padding:6px;}
QPushButton#suggest {background:#f1edff;color:#5a3df0;border:0;border-radius:12px;padding:6px 12px;font-size:12px;font-weight:700;}
QPushButton#suggest:hover {background:#e6dfff;color:#4a33c9;}
'''
STYLE = STYLE.replace('CHEVRON', (Path(__file__).parent/'resources'/'chevron.svg').as_posix())




def load_fonts():
    """Register the bundled OFL fonts (Manrope UI, Sora display); safe to call repeatedly."""
    from PySide6.QtGui import QFontDatabase
    for path in sorted((Path(__file__).parent/'resources'/'fonts').glob('*.ttf')):
        QFontDatabase.addApplicationFont(str(path))


def step(number, text):
    row = QWidget(); row.setObjectName('step'); layout = QHBoxLayout(row)
    layout.setContentsMargins(0,0,0,0); layout.setSpacing(10)
    layout.addWidget(label(str(number),'badge')); layout.addWidget(label(text,'section')); layout.addStretch()
    return row


def label(text, kind=None):
    item = QLabel(text)
    if kind:
        item.setObjectName(kind)
    return item


def panel(kind='panel'):
    frame = QFrame()
    frame.setObjectName(kind)
    shadow = QGraphicsDropShadowEffect(frame)
    shadow.setBlurRadius(30); shadow.setOffset(0,6); shadow.setColor(QColor(60,40,140,22))
    frame.setGraphicsEffect(shadow)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18,18,18,18)
    layout.setSpacing(12)
    return frame, layout


DIRECTORS=[('Local AI director • on this computer (Ollama)','local'),('Activity engine • no AI','activity'),
           ('Claude vision editor • cloud, optional','claude')]


CHAT_SUGGESTIONS = ['Make it faster and more intense', 'Slow motion only on the biggest hits',
                    'Use this song: <paste a link>', 'Make a 30 second Shorts version', 'Why did you open with that shot?']


class ChatJob(QThread):
    """One director chat turn off the UI thread."""
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, operation):
        super().__init__()
        self.operation = operation

    def run(self):
        try:
            self.done.emit(self.operation())
        except Exception as error:
            self.failed.emit(str(error))


class RenderJob(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float, str)

    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.cancel = threading.Event()

    def run(self):
        try:
            with jobs.job(self.cancel, lambda fraction, message: self.progress.emit(fraction, message)):
                self.done.emit(self.operation())
        except jobs.Cancelled:
            self.failed.emit(CANCELLED)
        except Exception as error:
            self.failed.emit(str(error))


class Studio(QMainWindow):
    def __init__(self, preferences=None):
        super().__init__()
        self.preferences=preferences if preferences is not None else QSettings("DRIFT", "MontageStudio")
        self.music_folder=str(self.preferences.value("music_folder", ""))
        self.setAcceptDrops(True)
        self.setWindowTitle('DRIFT • Montage Studio')
        self.resize(1520,1000)
        self.setMinimumSize(1200,820)
        self.music_path = None
        self.timeline = None
        self.last_output = None
        self.job = None
        load_fonts()
        root = QWidget()
        self.setCentralWidget(root)
        page = QVBoxLayout(root)
        page.setContentsMargins(0,0,0,0); page.setSpacing(0)
        bar=QFrame(); bar.setObjectName('appbar'); bar.setFixedHeight(66)
        bar_layout=QHBoxLayout(bar); bar_layout.setContentsMargins(24,0,24,0); bar_layout.setSpacing(6)
        bar_layout.addWidget(BrandMark()); bar_layout.addSpacing(6)
        bar_layout.addWidget(label('DRIFT','brand')); bar_layout.addSpacing(4)
        bar_layout.addWidget(label('Montage Studio','muted')); bar_layout.addSpacing(30)
        self.nav_buttons={}
        for name,callback in [('Studio',lambda:self.screen.setCurrentIndex(0)),
                              ('Import',self.import_media),('AI Director',lambda:self.show_advanced(self.director_mode)),
                              ('Timeline',lambda:self.body_scroll.ensureWidgetVisible(self.lanes)),
                              ('AI Chat',lambda:(self.body_scroll.ensureWidgetVisible(self.chat_panel),self.chat_input.setFocus())),
                              ('Effects',lambda:self.show_advanced(self.transition)),
                              ('Audio',self.import_music),
                              ('Export',self.export)]:
            button=QPushButton(name);button.setObjectName('nav')
            self.nav_buttons[name]=button
            if name=='Studio':button.setCheckable(True);button.setChecked(True)
            button.clicked.connect(callback)
            bar_layout.addWidget(button)
        bar_layout.addStretch()
        for text,kind in [('Beat-synced','chip'),('Local render','chipTeal')]:
            bar_layout.addWidget(label(text,kind),0,Qt.AlignVCenter)
        page.addWidget(bar)
        body=QWidget();body.setObjectName('canvas')
        self.body_scroll=QScrollArea();self.body_scroll.setWidgetResizable(True)
        self.body_scroll.setFrameShape(QFrame.NoFrame)
        self.body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body_scroll.setWidget(body);page.addWidget(self.body_scroll,1)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24,20,24,20); layout.setSpacing(16)
        self.banner=CathedralBanner(); layout.addWidget(self.banner)
        workspace = QSplitter(Qt.Horizontal)
        workspace.setChildrenCollapsible(False)
        self.workspace=workspace
        layout.addWidget(workspace,1)
        main=QWidget(); main.setObjectName('canvas'); column=QVBoxLayout(main)
        column.setContentsMargins(0,0,0,0); column.setSpacing(16)
        top=QHBoxLayout(); top.setSpacing(16)

        intake,intake_layout=panel('create')
        intake_layout.addWidget(step(1,'Start your edit'))
        drop=QFrame(); drop.setObjectName('dropzone'); drop_layout=QVBoxLayout(drop)
        drop_layout.setContentsMargins(16,14,16,14); drop_layout.setSpacing(8)
        self.drop_hint=label('Drop gameplay clips here, or import them. Add a song and we’ll build the edit.','muted')
        self.drop_hint.setWordWrap(True); drop_layout.addWidget(self.drop_hint)
        self.footage = QListWidget(); self.footage.setMinimumHeight(84); self.footage.setMaximumHeight(120)
        drop_layout.addWidget(self.footage)
        clip_row=QHBoxLayout()
        self.import_button = QPushButton('+ Import gameplay')
        self.import_button.clicked.connect(self.import_media); clip_row.addWidget(self.import_button)
        remove = QPushButton('Remove')
        remove.clicked.connect(lambda: self.footage.takeItem(self.footage.currentRow())); clip_row.addWidget(remove)
        drop_layout.addLayout(clip_row)
        drop.setMinimumHeight(196); intake_layout.addWidget(drop)
        intake_layout.addWidget(label('SOUNDTRACK','eyebrow'))
        song_row=QHBoxLayout()
        self.song_name=QLineEdit();self.song_name.setPlaceholderText('Any song: paste a YouTube/Spotify link, a file path, or type a title…')
        self.song_name.setToolTip('Paste a YouTube or Spotify track link, drop or browse to any audio/video file, '
                                  'or type a title from your music folder. Press Enter to load it.')
        self.song_name.textEdited.connect(lambda:self.clear_music_selection())
        self.song_name.returnPressed.connect(lambda:self.resolve_song())
        song_row.addWidget(self.song_name,1)
        library=QPushButton('Music folder');library.clicked.connect(self.choose_music_folder);song_row.addWidget(library)
        self.link_button=QPushButton('Add from link');self.link_button.setToolTip('Paste a YouTube video or Spotify track link')
        self.link_button.clicked.connect(self.add_music_link)
        intake_layout.addLayout(song_row)
        self.music_label = label('No music selected','muted'); self.music_label.setWordWrap(True)
        music_row=QHBoxLayout(); music_row.addWidget(self.music_label,1)
        music = QPushButton('Choose file'); music.clicked.connect(self.import_music); music_row.addWidget(music)
        music_row.addWidget(self.link_button)
        intake_layout.addLayout(music_row)
        intake_layout.addStretch()
        chips=QHBoxLayout(); chips.setSpacing(6)
        for text,kind in [('Beat grid','chip'),('Speed ramps','chipPink'),('Punch-ins','chipAmber'),('Mastered audio','chipTeal')]:
            chips.addWidget(label(text,kind))
        chips.addStretch(); intake_layout.addLayout(chips)
        self.export_preset=QComboBox()
        for title,key in [('YouTube • 1080p 30 fps','youtube-1080p30'),('YouTube • 1080p 60 fps','youtube-1080p60'),
                          ('YouTube • 1440p 60 fps • master','youtube-1440p60'),('Shorts / TikTok • 1080×1920','shorts-1080x1920'),
                          ('Instagram • 1080×1350','instagram-1080x1350'),('Custom • Creative controls','custom')]:
            self.export_preset.addItem(title,key)
        preset_row=QHBoxLayout();preset_row.addWidget(label('EXPORT FOR','eyebrow'));preset_row.addWidget(self.export_preset,1)
        intake_layout.addLayout(preset_row)
        self.pace=QComboBox()
        for title,key in [('Balanced • 1.5–4 s shots','balanced'),('Calm • 2–5 s shots','calm'),
                          ('Fast • 1–3 s shots','fast'),('Hyper • 0.75–2.25 s shots','hyper')]:
            self.pace.addItem(title,key)
        pace_row=QHBoxLayout();pace_row.addWidget(label('PACE','eyebrow'));pace_row.addWidget(self.pace,1)
        intake_layout.addLayout(pace_row)
        self.create_button=QPushButton('Create montage');self.create_button.setObjectName('primary')
        self.create_button.clicked.connect(lambda:self.export(automatic=True))
        intake_layout.addWidget(self.create_button)
        preview_row=QHBoxLayout()
        self.preview_button=QPushButton('Quick preview');self.preview_button.setToolTip('Fast low-resolution draft of the same edit')
        self.preview_button.clicked.connect(lambda:self.export(automatic=True,preview=True));preview_row.addWidget(self.preview_button)
        self.finalize_button=QPushButton('Render final from preview');self.finalize_button.setEnabled(False)
        self.finalize_button.setToolTip('Render the previewed edit at full quality without re-analysing')
        self.finalize_button.clicked.connect(self.finalize_preview);preview_row.addWidget(self.finalize_button)
        intake_layout.addLayout(preview_row)
        self.preview_timeline=None
        secondary=QHBoxLayout()
        advanced=QPushButton('Creative controls');advanced.clicked.connect(self.toggle_advanced);secondary.addWidget(advanced)
        load = QPushButton('Open timeline'); load.clicked.connect(self.load_timeline); secondary.addWidget(load)
        intake_layout.addLayout(secondary)
        intake.setMinimumWidth(380); intake.setMinimumHeight(intake.sizeHint().height())
        top.addWidget(intake,5)

        preview,view = panel()
        view.addWidget(step(2,'Preview'))
        self.preview_title = label('Your footage, in focus','muted')
        view.addWidget(self.preview_title)
        self.video = QVideoWidget(); self.video.setStyleSheet("background:#000000;")
        self.video.setMinimumHeight(150)
        self.screen = QStackedWidget();self.screen.setMinimumHeight(300)
        empty = CinemaCanvas(); empty_layout = QVBoxLayout(empty)
        empty_layout.addStretch(3)
        message = label('NO MEDIA LOADED', 'eyebrow')
        message.setAlignment(Qt.AlignCenter); empty_layout.addWidget(message)
        message = label('Every moment has a story.', 'title')
        message.setAlignment(Qt.AlignCenter); empty_layout.addWidget(message)
        message = label('Your clips and finished montage will play here.', 'muted')
        message.setAlignment(Qt.AlignCenter); empty_layout.addWidget(message)
        empty_layout.addStretch(1)
        self.screen.addWidget(empty); self.screen.addWidget(self.video)
        view.addWidget(self.screen,1)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        controls = QHBoxLayout()
        self.play_button = QPushButton('Play / Pause');self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.toggle_play)
        controls.addWidget(self.play_button)
        self.scrub = QSlider(Qt.Horizontal);self.scrub.setEnabled(False)
        self.scrub.sliderMoved.connect(self.player.setPosition)
        self.player.positionChanged.connect(self.scrub.setValue)
        self.player.durationChanged.connect(lambda duration:self.scrub.setRange(0,duration))
        controls.addWidget(self.scrub,1)
        self.clock = label('00:00','muted')
        self.player.positionChanged.connect(lambda t:self.clock.setText(f'{t//60000:02d}:{t//1000%60:02d}'))
        controls.addWidget(self.clock)
        view.addLayout(controls)
        top.addWidget(preview,7)
        column.addLayout(top)

        timeline,track = panel()
        heading=QHBoxLayout(); heading.addWidget(step(3,'Edit timeline'),1)
        for text,kind in [('Footage','chip'),('Music','chipTeal'),('Dialogue','chipAmber')]:
            heading.addWidget(label(text,kind))
        track.addLayout(heading)
        self.timeline_table = QTableWidget(0,4)
        self.timeline_table.setHorizontalHeaderLabels(['Footage','Source in','Length','Activity'])
        self.timeline_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.timeline_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.timeline_table.setAlternatingRowColors(True)
        self.lanes=TimelineLanes()
        self.lanes.seek.connect(self.seek_export)
        self.player.positionChanged.connect(lambda t:self.lanes.set_position(t/1000))
        track.addWidget(self.lanes)
        track.addWidget(self.timeline_table)
        self.timeline_table.hide()
        edit_row=QHBoxLayout()
        self.edit_buttons=[]
        for text,action in [('◀ Move shot earlier',lambda:self.move_selected(-1)),('Move shot later ▶',lambda:self.move_selected(1)),
                            ('Swap with alternate…',self.swap_selected)]:
            button=QPushButton(text);button.clicked.connect(action);button.setEnabled(False)
            edit_row.addWidget(button);self.edit_buttons.append(button)
        edit_row.addStretch();track.addLayout(edit_row)
        self.alternates=[]
        track.addWidget(label('Built from the generated or loaded timeline. Manual clip editing is planned.','muted'))
        column.addWidget(timeline)

        chat,talk=panel()
        chat_heading=QHBoxLayout();chat_heading.addWidget(step(4,'Director chat'),1)
        self.chat_chip=label('On this computer','chipTeal');chat_heading.addWidget(self.chat_chip)
        talk.addLayout(chat_heading)
        talk.addWidget(label('Ask for changes in your own words. The director explains its choices and adjusts '
                             'the edit for you; every change goes through the same controls you can see.','muted'))
        self.chat_log=QTextBrowser();self.chat_log.setObjectName('chatlog');self.chat_log.setOpenLinks(False)
        self.chat_log.setMinimumHeight(170);self.chat_log.setMaximumHeight(260)
        talk.addWidget(self.chat_log)
        suggestions=QHBoxLayout();suggestions.setSpacing(6)
        for text in CHAT_SUGGESTIONS[:4]:
            chip=QPushButton(text);chip.setObjectName('suggest')
            chip.clicked.connect(lambda _=False,t=text:self.use_suggestion(t));suggestions.addWidget(chip)
        suggestions.addStretch();talk.addLayout(suggestions)
        ask_row=QHBoxLayout()
        self.chat_input=QLineEdit();self.chat_input.setPlaceholderText('Tell the director what you want… e.g. “more slow-mo on the drop”')
        self.chat_input.returnPressed.connect(self.send_chat);ask_row.addWidget(self.chat_input,1)
        self.chat_send=QPushButton('Send');self.chat_send.setObjectName('primary');self.chat_send.clicked.connect(self.send_chat)
        ask_row.addWidget(self.chat_send);talk.addLayout(ask_row)
        self.chat_panel=chat;self.chat_job=None;self.chat_session=None;self.last_report=None
        column.addWidget(chat)
        self.progress = QProgressBar(); self.progress.setRange(0,1); self.progress.setValue(0); self.progress.setTextVisible(False)
        progress_row=QHBoxLayout(); progress_row.addWidget(self.progress,1)
        self.cancel_button=QPushButton('Cancel');self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_job);progress_row.addWidget(self.cancel_button)
        column.addLayout(progress_row)
        self.status = label('Ready for your footage.','status')
        self.status.setWordWrap(True); column.addWidget(self.status)
        column.addStretch()
        main.setMinimumHeight(main.sizeHint().height())
        workspace.addWidget(main)
        inspector,right = panel()
        right.addWidget(step(5,'Creative controls'))
        right.addWidget(label('Shape the story.','title'))
        self.analysis_label=label('SCENE ANALYSIS\nImport footage and choose Analyze.\nMotion/audio scores are heuristic; kill detection is planned.','muted')
        self.analysis_label.setWordWrap(True);right.addWidget(self.analysis_label)
        right.addWidget(label('Add narration, references, or a quiet closing thought.','muted'))
        self.dialogue = QTableWidget(0,6)
        self.dialogue.setHorizontalHeaderLabels(['Audio','At','In','Length','Reference','Kind'])
        self.dialogue.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.dialogue.setMinimumHeight(100);self.dialogue.setMaximumHeight(155)
        self.dialogue.setToolTip('Editable timing in seconds. Reference is metadata, not a rendered caption.')
        right.addWidget(self.dialogue)
        add = QPushButton('+ Add dialogue recording')
        add.clicked.connect(self.add_dialogue)
        right.addWidget(add)
        delete = QPushButton('Remove selected dialogue')
        delete.clicked.connect(lambda:self.dialogue.removeRow(self.dialogue.currentRow()))
        right.addWidget(delete)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.director_mode=QComboBox()
        for title,key in DIRECTORS:self.director_mode.addItem(title,key)
        form.addRow('AI director',self.director_mode)
        self.director_note=QLabel('Claude reviews sampled frames of your footage to pick highlights. '
                                  'Frames are sent to Anthropic; needs ANTHROPIC_API_KEY or ant auth login.')
        self.director_note.setWordWrap(True)
        self.director_note.setVisible(False)
        self.director_mode.currentIndexChanged.connect(lambda i:self.director_note.setVisible(self.director_mode.itemData(i)=='claude'))
        form.addRow(self.director_note)
        self.ai_model=QLineEdit(LOCAL_MODEL);self.ai_model.setPlaceholderText('Ollama vision model, e.g. '+LOCAL_MODEL)
        self.director_mode.currentIndexChanged.connect(lambda i:self.ai_model.setEnabled(self.director_mode.itemData(i)=='local'))
        form.addRow('Local vision model',self.ai_model)
        self.local_status=QLabel('Runs on this computer with Ollama • your footage never leaves it.')
        self.local_status.setWordWrap(True)
        form.addRow(self.local_status)
        self.setup_button=QPushButton('Set up local AI')
        self.setup_button.clicked.connect(self.setup_local_ai)
        self.director_mode.currentIndexChanged.connect(lambda i:self.setup_button.setEnabled(self.director_mode.itemData(i)=='local'))
        form.addRow(self.setup_button)
        self.ai_brief=QLineEdit();self.ai_brief.setPlaceholderText('Describe the feeling, pace, or message…')
        form.addRow('Creative brief',self.ai_brief)
        self.story_tone=QComboBox()
        for key,(title,closing,brief) in STORY_TONES.items():
            self.story_tone.addItem(title,key)
        form.addRow('Story tone',self.story_tone)
        self.closing_line=QLineEdit('Keep the faith.');self.closing_line.setMaxLength(140)
        self.closing_line.setPlaceholderText('Optional closing line')
        form.addRow('Closing line',self.closing_line)
        self.story_tone.currentIndexChanged.connect(self.update_story_tone)

        self.transition = QComboBox()
        for title,key in [('Hard cut','cut'),('Fade through black','fade_black'),('Fade through white','fade_white'),('Motion zoom','zoom'),('Cinematic blend sequence','cinematic'),('Smooth push','push'),('Zoom blend','zoom_blend'),('Blur blend','blur'),('Dissolve','dissolve')]:
            self.transition.addItem(title,key)
        form.addRow('Transition',self.transition)
        self.fade = QDoubleSpinBox(); self.fade.setRange(.05,1); self.fade.setSingleStep(.05); self.fade.setValue(.2)
        form.addRow('Transition seconds',self.fade)
        self.duration = QDoubleSpinBox(); self.duration.setRange(1,3600); self.duration.setValue(30)
        form.addRow('Target seconds',self.duration)
        self.resolution = QComboBox()
        for title,size in [('HD • 1280 × 720',(1280,720)),('Full HD • 1920 × 1080',(1920,1080)),('Portrait • 1080 × 1920',(1080,1920))]:
            self.resolution.addItem(title,size)
        self.resolution.setCurrentIndex(1)
        form.addRow('Canvas',self.resolution)
        self.quality = QComboBox()
        for title,key in [('High quality','high'),('Master quality • larger files','master'),('Draft • fast preview','draft')]:
            self.quality.addItem(title,key)
        form.addRow('Render quality',self.quality)
        self.look=QComboBox()
        for title,key in [('Clean • subtle contrast','clean'),('Punchy • vivid','punchy'),
                          ('Cinematic • warm/cool balance','cinematic'),('Film • cinematic grade with grain','film'),
                          ('Monochrome','mono'),('Original colour','none')]:
            self.look.addItem(title,key)
        form.addRow('Look',self.look)
        self.slowmo=QComboBox()
        for title,key in [('Smooth (motion interpolation)','motion'),('Blended frames • faster','blend'),('Held frames • fastest','none')]:
            self.slowmo.addItem(title,key)
        form.addRow('Slow motion',self.slowmo)
        self.motion_blur=QCheckBox('Motion blur on speed ramps');self.motion_blur.setChecked(True)
        form.addRow(self.motion_blur)
        self.sfx=QCheckBox('Transition swishes (quiet, on push/zoom blends)');self.sfx.setChecked(True)
        form.addRow(self.sfx)
        self.auto_music_section = QCheckBox('Choose an energetic section of my song')
        self.auto_music_section.setChecked(True)
        form.addRow(self.auto_music_section)
        self.fps = QSpinBox(); self.fps.setRange(1,120); self.fps.setValue(30)
        form.addRow('Frames / second',self.fps)
        self.tempo_override=QDoubleSpinBox();self.tempo_override.setRange(0,240);self.tempo_override.setDecimals(1)
        self.tempo_override.setSpecialValueText('Automatic (measured)');self.tempo_override.setSuffix(' BPM')
        self.tempo_override.setToolTip('Correct the beat grid if the measured tempo is wrong. 0 = automatic.')
        tap_row=QHBoxLayout();tap_row.addWidget(self.tempo_override,1)
        self.tap_button=QPushButton('Tap tempo');self.tap_button.setToolTip('Tap along with the beat (4+ taps)')
        self.tap_button.clicked.connect(self.tap_tempo);tap_row.addWidget(self.tap_button)
        tap_widget=QWidget();tap_widget.setObjectName('step');tap_widget.setLayout(tap_row);tap_row.setContentsMargins(0,0,0,0)
        form.addRow('Tempo',tap_widget)
        self.first_downbeat=QDoubleSpinBox();self.first_downbeat.setRange(0,3600);self.first_downbeat.setDecimals(2)
        self.first_downbeat.setSuffix(' s');self.first_downbeat.setToolTip('Song time of any bar start (beat 1). Used with a tempo override.')
        form.addRow('First downbeat',self.first_downbeat)
        self.taps=[]
        form_widget=QWidget();form_widget.setLayout(form);form_widget.setMinimumHeight(350)
        right.addWidget(form_widget)
        right.addStretch()
        right.addWidget(label('H.264 / AAC  •  CPU RENDER','eyebrow'))
        self.export_button = QPushButton('Generate and export montage'); self.export_button.setObjectName('primary')
        self.export_button.clicked.connect(self.export)
        right.addWidget(self.export_button)
        self.replay_button = QPushButton('Render loaded timeline')
        self.replay_button.setToolTip('Uses stored timeline settings and dialogue; inspector changes apply to new generation.')
        self.replay_button.setEnabled(False); self.replay_button.clicked.connect(lambda:self.export(replay=True))
        right.addWidget(self.replay_button)
        self.formats_button = QPushButton('Export every format • YouTube, Shorts, Instagram')
        self.formats_button.setToolTip('Deliver the loaded edit as 16:9, 9:16 and 4:5 with action-following crops')
        self.formats_button.setEnabled(False); self.formats_button.clicked.connect(self.export_formats)
        right.addWidget(self.formats_button)
        self.open_button = QPushButton('Open export folder')
        self.open_button.setEnabled(False); self.open_button.clicked.connect(self.open_export)
        right.addWidget(self.open_button)
        inspector.setMinimumHeight(960)
        inspector_scroll=QScrollArea();inspector_scroll.setWidgetResizable(True);inspector_scroll.setWidget(inspector)
        inspector_scroll.setMinimumWidth(360);inspector_scroll.setMaximumWidth(440);workspace.addWidget(inspector_scroll)
        self.inspector_scroll=inspector_scroll;inspector_scroll.hide()
        workspace.setSizes([1100,400])
        self.footage.currentTextChanged.connect(self.preview_file)
        self.player.errorOccurred.connect(lambda error,message:self.status.setText('Preview: '+message))
        saved_model=str(self.preferences.value('local_model',LOCAL_MODEL)) or LOCAL_MODEL
        # The earlier default measured poorly (0/5 death screens); move people still on it.
        self.ai_model.setText(LOCAL_MODEL if saved_model=='qwen2.5vl:7b' else saved_model)
        saved=self.preferences.value('director',None)
        if saved is None:   # earlier versions stored an index: 0 activity (default), 1 Ollama text, 2 Claude
            saved={'2':'claude'}.get(str(self.preferences.value('director_mode',0)),'local')
        self.director_mode.setCurrentIndex(max(0,self.director_mode.findData(saved)))
        self.ai_brief.setText(str(self.preferences.value('brief','')))
        self.pace.setCurrentIndex(max(0,self.pace.findData(str(self.preferences.value('pace','balanced')))))
        self.pace.currentIndexChanged.connect(self.save_preferences)
        self.ai_model.editingFinished.connect(self.save_preferences)
        self.director_mode.currentIndexChanged.connect(self.save_preferences)
        self.ai_brief.editingFinished.connect(self.save_preferences)
        self.status.setText('Ready for your footage • Drop clips and choose a soundtrack to begin.')
        tone=str(self.preferences.value('story_tone','subtle'))
        stored_line=self.preferences.value('closing_line',None)
        self.story_tone.blockSignals(True)
        self.story_tone.setCurrentIndex(max(0,self.story_tone.findData(tone)))
        self.story_tone.blockSignals(False)
        self.closing_line.setText(str(stored_line) if stored_line is not None else STORY_TONES[self.story_tone.currentData()][1])
        self.closing_line.editingFinished.connect(self.save_preferences)

    def save_preferences(self,*args):
        for key,value in [('music_folder',self.music_folder),('local_model',self.ai_model.text().strip()),
                          ('director',self.director_mode.currentData()),('brief',self.ai_brief.text().strip()),
                          ('story_tone',self.story_tone.currentData()),('pace',self.pace.currentData()),('closing_line',self.closing_line.text())]:
            self.preferences.setValue(key,value)

    def update_story_tone(self,*args):
        defaults={values[1] for values in STORY_TONES.values()}
        if self.closing_line.text() in defaults:
            self.closing_line.setText(STORY_TONES[self.story_tone.currentData()][1])
        self.save_preferences()

    def ai_director(self):
        """The chosen AI editor (None for the activity engine); the local model must be ready."""
        mode=self.director_mode.currentData()
        if mode=='claude':
            from .vision_director import ClaudeDirector
            return ClaudeDirector()
        if mode!='local':return None
        from .local_ai import readiness
        from .vision_director import LocalDirector
        model=self.ai_model.text().strip() or LOCAL_MODEL
        ready,message=readiness(model)
        self.local_status.setText(message)
        if not ready:raise ValueError(message+' Or choose the activity engine under AI director.')
        return LocalDirector(model)

    def setup_local_ai(self):
        """Check Ollama and download the chosen vision model through it, with progress and cancel."""
        from .local_ai import INSTALL_URL, RECOMMENDED, pull, readiness, status, valid_name
        model=self.ai_model.text().strip() or LOCAL_MODEL
        if not valid_name(model):
            QMessageBox.warning(self,'Local AI','Enter a model name such as '+LOCAL_MODEL);return
        state=status()
        if not state['running']:
            self.local_status.setText('Ollama is not running. Install it, start it, then press Set up again.')
            if QMessageBox.question(self,'Local AI','Ollama runs the AI director on this computer. '
                                    'Open the Ollama download page?')==QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(INSTALL_URL))
            return
        ready,message=readiness(model)
        if ready:
            self.local_status.setText(message);return
        if self.job is not None:
            QMessageBox.information(self,'Local AI','Wait for the current job to finish.');return
        size=next((f' (about {m["size_gb"]:g} GB)' for m in RECOMMENDED if m['name']==model),'')
        if QMessageBox.question(self,'Local AI',f'Download {model}{size} with Ollama? It stays on this computer.')!=QMessageBox.Yes:
            return
        self.job=RenderJob(lambda:pull(model,progress=jobs.report))
        self.job.done.connect(lambda _:self.local_status.setText(readiness(model)[1]))
        self.job.failed.connect(lambda m:self.local_status.setText('Download stopped • '+m))
        self.job.progress.connect(self.on_progress)
        self.job.finished.connect(self.setup_finished)
        self.setup_button.setEnabled(False);self.create_button.setEnabled(False);self.cancel_button.setEnabled(True)
        self.job.start()

    def setup_finished(self):
        self.job.deleteLater();self.job=None;self.setup_button.setEnabled(True);self.create_button.setEnabled(True)
        self.cancel_button.setEnabled(False);self.progress.setRange(0,1);self.progress.setValue(1)

    def show_advanced(self,target=None):
        self.inspector_scroll.show()
        if target is not None:target.setFocus();self.inspector_scroll.ensureWidgetVisible(target)

    def toggle_advanced(self):
        visible=self.inspector_scroll.isHidden()
        self.inspector_scroll.setVisible(visible)

    def clear_music_selection(self):
        self.music_path=None

    def choose_music_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Choose the folder containing your songs',self.music_folder)
        if folder:
            self.music_folder=folder;self.save_preferences()
            self.status.setText('Music folder saved. Type a song title or artist and title; DRIFT matches local filenames.')

    def music_library(self):
        music=QStandardPaths.writableLocation(QStandardPaths.MusicLocation)
        return Path(music)/'DRIFT' if music else default_library()

    def resolve_song(self,then=None):
        """Turn whatever is in the song box into a song. Links download first, then ``then`` runs."""
        if self.music_path and Path(self.music_path).is_file():return True
        kind,value=interpret_song(self.song_name.text())
        if kind=='link':
            self.add_music_link(value,then=then);return False
        if kind=='file':
            self.select_music(value);return True
        try:
            if kind=='empty':
                QMessageBox.information(self,'Choose your music','Paste a YouTube or Spotify link, drop a song file, '
                                        'or type a song title.');return False
            library=self.music_library()
            matches=search_libraries([self.music_folder,library],value)
            if not matches and not self.music_folder:
                self.choose_music_folder()
                if not self.music_folder:return False
                matches=search_libraries([self.music_folder],value)
            if not matches:
                QMessageBox.information(self,'Song not found','No matching song in your music folders. Paste a YouTube or Spotify link instead, try artist and title, or drop the song file.');return False
            if len(matches)>1:
                names=[str(p) for p in matches]
                choice,ok=QInputDialog.getItem(self,'Choose your song','Several files match:',names,0,False)
                if not ok:return False
                path=choice
            else:path=str(matches[0])
            self.select_music(path);return True
        except ValueError as error:
            QMessageBox.information(self,'Choose your music',str(error));return False

    def select_music(self,path):
        self.music_path=str(Path(path).resolve())
        self.song_name.setText(Path(path).stem);self.music_label.setText(Path(path).name)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in VIDEO|AUDIO for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:event.ignore()

    def dropEvent(self,event):
        self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

    def add_files(self,files):
        existing={self.footage.item(i).text() for i in range(self.footage.count())}
        audio=[];ignored=0
        for path in files:
            path=Path(path)
            if not path.is_file():ignored+=1;continue
            resolved=str(path.resolve())
            if path.suffix.lower() in VIDEO:
                if resolved not in existing:self.footage.addItem(resolved);existing.add(resolved)
            elif path.suffix.lower() in AUDIO:audio.append(resolved)
            else:ignored+=1
        if len(audio)==1:self.select_music(audio[0])
        elif len(audio)>1:
            choice,ok=QInputDialog.getItem(self,'Choose music','Use which dropped audio file?',audio,0,False)
            if ok:self.select_music(choice)
        if self.footage.count():
            self.footage.setCurrentRow(0)
        self.drop_hint.setText(f'{self.footage.count()} gameplay clips ready. '+('Music selected.' if self.music_path else 'Type your song title.'))
        if ignored:self.status.setText(f'Ignored {ignored} unsupported or missing files.')


    def replay_export(self):
        if self.timeline is None:
            QMessageBox.information(self,'Open a project','Generate or open a timeline first.');return
        self.export(replay=True)

    def analyze_sources(self):
        if self.job is not None:return
        sources=[self.footage.item(i).text() for i in range(self.footage.count())]
        if not sources:
            QMessageBox.information(self,'Import footage','Add gameplay before analyzing.');return
        settings=Settings()
        def analyze():
            return [candidate for path in sources for candidate in analyze_gameplay(probe(path),settings)]
        self.job=RenderJob(analyze)
        self.progress.setRange(0,0);self.status.setText('Analyzing source motion and audio activity…')
        self.export_button.setEnabled(False);self.replay_button.setEnabled(False)
        self.job.done.connect(self.show_analysis);self.job.failed.connect(self.failed);self.job.finished.connect(self.finished)
        self.job.start()

    def show_analysis(self,candidates):
        skipped=[c for c in candidates if c.get('exclude')]
        ranked=sorted((c for c in candidates if not c.get('exclude')),key=lambda c:-c['score'])
        if ranked:
            top=ranked[0]
            self.analysis_label.setText(f"SCENE ANALYSIS\n{len(ranked)} candidate moments\nTop activity: {top['score']:.3f} (not confidence)\n{Path(top['source']).name} at {top['time']:.2f}s\n{len(skipped)} non-gameplay spans skipped (HUD hidden: deaths, scoreboards, menus).")
        self.status.setText(f'Analysis complete • {len(ranked)} candidate moments, {len(skipped)} non-gameplay spans skipped. Ready to generate.')

    def import_media(self):
        files,_ = QFileDialog.getOpenFileNames(self,'Import gameplay','','Video (*.mp4 *.mkv *.mov *.webm);;All files (*)')
        self.add_files(files)

    def import_music(self):
        path,_ = QFileDialog.getOpenFileName(self,'Choose music','',
                                             'Audio or video with sound (*.wav *.mp3 *.flac *.m4a *.ogg *.opus *.aac *.mp4 *.mkv *.mov *.webm);;All files (*)')
        if path: self.select_music(path)

    def add_music_link(self,link=None,then=None):
        from .music_sources import NOTICE, add_music, classify
        if self.job is not None:
            QMessageBox.information(self,'Busy','Wait for the current job to finish.');return
        if link is None:
            link,ok=QInputDialog.getText(self,'Add music from a link','YouTube video or Spotify track link:\n\n'+NOTICE)
            if not ok or not link.strip():return
        try:
            classify(link)
        except ValueError as error:
            QMessageBox.information(self,'Unsupported link',str(error));return
        folder=self.music_folder if self.music_folder and Path(self.music_folder).is_dir() else str(self.music_library())
        Path(folder).mkdir(parents=True,exist_ok=True)
        self.after_music=then
        self.status.setText('Fetching music from link…')
        self.link_button.setEnabled(False);self.progress.setRange(0,0)
        self.job=RenderJob(lambda:add_music(link,folder))
        self.job.done.connect(self.music_link_added)
        self.job.failed.connect(lambda message:(self.status.setText('Could not add music • '+message),
                                                QMessageBox.warning(self,'Could not add music',message)))
        self.job.finished.connect(self.music_link_finished)
        self.job.start()

    def music_link_added(self,result):
        self.select_music(result['path'])
        origin={'local library':'Found in your music folder','youtube':'Added from YouTube',
                'youtube match for spotify track':'Added the YouTube match for this Spotify track'}.get(result['source'],'Added')
        self.status.setText(f"{origin} • {Path(result['path']).name}")

    def music_link_finished(self):
        self.progress.setRange(0,1);self.progress.setValue(1)
        self.link_button.setEnabled(True)
        self.job.deleteLater();self.job=None
        then,self.after_music=getattr(self,'after_music',None),None
        if then is not None and self.music_path and Path(self.music_path).is_file():
            QTimer.singleShot(0,then)   # carry on with what the user asked for (e.g. Create montage)

    def preview_file(self,path):
        if path:
            self.screen.setCurrentIndex(1)
            self.play_button.setEnabled(True);self.scrub.setEnabled(True)
            self.player.setSource(QUrl.fromLocalFile(path)); self.preview_title.setText(Path(path).name)

    def toggle_play(self):
        if self.player.playbackState()==QMediaPlayer.PlayingState: self.player.pause()
        else: self.player.play()

    def add_dialogue(self):
        path,_ = QFileDialog.getOpenFileName(self,'Choose narration or reference audio')
        if path:
            row=self.dialogue.rowCount(); self.dialogue.insertRow(row)
            for col,value in enumerate([path,'0','0','3','Add source / verse reference','original']):
                self.dialogue.setItem(row,col,QTableWidgetItem(value))

    def story(self):
        cues=[]
        for row in range(self.dialogue.rowCount()):
            values=[self.dialogue.item(row,i).text() for i in range(6)]
            cues.append(dict(source=values[0],at=float(values[1]),start=float(values[2]),duration=float(values[3]),
                             reference=values[4],text_kind=values[5]))
        story=dict(dialogue=cues,transition=self.transition.currentData(),transition_duration=self.fade.value(),
                   faith_message=self.closing_line.text().strip(),look=self.look.currentData(),
                   interpolation=self.slowmo.currentData(),motion_blur=self.motion_blur.isChecked(),
                   sfx='swish' if self.sfx.isChecked() else 'none',reframe='auto')
        if self.tempo_override.value()>=40:
            story['beat_override']=dict(bpm=self.tempo_override.value(),first_downbeat=self.first_downbeat.value())
        return story

    def tap_tempo(self):
        import time
        now=time.monotonic()
        if self.taps and not 0<now-self.taps[-1]<=2.0:self.taps=[]
        self.taps=(self.taps+[now])[-12:]
        if len(self.taps)>=4:
            bpm=60/float(np.median(np.diff(self.taps)))
            while bpm<70:bpm*=2
            while bpm>180:bpm/=2
            self.tempo_override.setValue(round(bpm,1))
            self.status.setText(f'Tapped tempo • {bpm:.1f} BPM (set First downbeat to a bar start in the song)')
        else:
            self.status.setText(f'Keep tapping… {len(self.taps)}/4')

    def show_timeline(self,timeline):
        self.timeline_table.show();self.timeline_table.setMaximumHeight(120)
        self.workspace.setMaximumHeight(720)
        self.timeline=timeline; self.lanes.set_timeline(timeline); self.replay_button.setEnabled(True)
        self.formats_button.setEnabled(True)
        for button in self.edit_buttons:button.setEnabled(True)
        self.timeline_table.setRowCount(len(timeline.clips))
        for row,clip in enumerate(timeline.clips):
            for col,value in enumerate([Path(clip.source).name,f'{clip.start:.2f}s',f'{clip.duration:.2f}s',f'{clip.score:.3f}']):
                self.timeline_table.setItem(row,col,QTableWidgetItem(value))

    def seek_export(self,seconds):
        if self.last_output and self.player.source().toLocalFile()==self.last_output:
            self.player.setPosition(round(seconds*1000))
        else:
            self.status.setText('Timeline seek becomes available after exporting this project.')

    def load_timeline(self):
        path,_=QFileDialog.getOpenFileName(self,'Open timeline','','Timeline (*.json)')
        if path:
            try: self.show_timeline(Timeline.load(path))
            except Exception as error: QMessageBox.warning(self,'Cannot load timeline',str(error));return
            analysis=Path(path).with_name(Path(path).name.replace('.timeline.json','.analysis.json'))
            try:self.alternates=[c for c in json.loads(analysis.read_text()).get('candidates',[]) if not c.get('exclude')]
            except (OSError,ValueError):self.alternates=[]

    def delivery_settings(self):
        key=self.export_preset.currentData()
        if key and key!='custom':
            settings=preset(key,duration=self.duration.value())
        else:
            width,height=self.resolution.currentData()
            settings=Settings(width=width,height=height,fps=self.fps.value(),duration=self.duration.value(),quality=self.quality.currentData())
        return with_pace(settings,self.pace.currentData())

    def export(self,checked=False,replay=False,automatic=False,preview=False,timeline=None):
        if self.job is not None: return
        if timeline is not None: replay=True   # finalising an existing edit needs no clips or song lookup
        if not replay and not self.footage.count():
            QMessageBox.information(self,'Add your clips','Drop gameplay clips into the window first.');return
        if not replay and not self.resolve_song(then=lambda:self.export(checked,replay,automatic,preview,timeline)):return
        if preview:
            cache=QStandardPaths.writableLocation(QStandardPaths.CacheLocation) or str(Path.home()/'.cache'/'drift')
            path=str(Path(cache)/'previews'/(datetime.now().strftime('preview-%Y%m%d-%H%M%S-')+uuid4().hex[:6]+'.mp4'))
        elif automatic or timeline is not None:
            movies=QStandardPaths.writableLocation(QStandardPaths.MoviesLocation) or str(Path.home()/'Videos')
            path=str(Path(movies)/'DRIFT'/(datetime.now().strftime('montage-%Y%m%d-%H%M%S-')+uuid4().hex[:6]+'.mp4'))
        else:
            path,_=QFileDialog.getSaveFileName(self,'Export montage','','MP4 (*.mp4)')
        if not path: return
        if not path.lower().endswith('.mp4'): path+='.mp4'
        try:
            if timeline is not None:
                replay=True
                operation=lambda:render(timeline,path)
            elif replay:
                timeline=self.timeline
                operation=lambda:render(timeline,path)
            else:
                settings=self.delivery_settings()
                if preview:settings=draft_of(settings)
                sources=[self.footage.item(i).text() for i in range(self.footage.count())]
                song=self.music_path; story=self.story()
                if automatic:
                    story.update(faith_message=self.closing_line.text().strip(),edit_profile='cinematic',
                                 gameplay_gain=.25,music_gain=.8,normalize_audio=True,transition='cinematic',punch_through=True,match_shots=True,bookends=True,impacts=True,
                                 beat_fx=True,target_lufs=-14.0,
                                 auto_music_section=self.auto_music_section.isChecked())
                if preview:story['interpolation']='blend'   # fast; the final render uses the chosen mode
                brief=self.ai_brief.text().strip() or STORY_TONES[self.story_tone.currentData()][2]
                editor=self.ai_director()
                operation=lambda:create_montage(sources,song,path,settings,story,None,brief,ai_editor=editor)
        except Exception as error:
            QMessageBox.warning(self,'Check story settings',str(error)); return
        self.create_button.setEnabled(False);self.create_button.setText('Creating your montage…')
        self.export_button.setEnabled(False); self.replay_button.setEnabled(False)
        self.progress.setRange(0,1000); self.progress.setValue(0); self.status.setText('Starting • The workspace stays responsive.')
        self.job=RenderJob(operation)
        self.job.done.connect(lambda report:self.completed(report,path,replay,preview))
        self.job.failed.connect(self.failed)
        self.job.finished.connect(self.finished)
        self.job.progress.connect(self.on_progress)
        self.cancel_button.setEnabled(True)
        self.job.start()

    def completed(self,report,path,replay,preview=False):
        self.last_output=path;self.last_report=report
        analysis=Path(path).with_suffix('.analysis.json')
        if analysis.is_file():
            try:self.alternates=[c for c in json.loads(analysis.read_text()).get('candidates',[]) if not c.get('exclude')]
            except (OSError,ValueError):self.alternates=[]
        if preview:
            self.preview_timeline=Path(path).with_suffix('.timeline.json')
            self.finalize_button.setEnabled(True)
        self.save_preferences()
        self.status.setText(f"Validated export • {report['duration']:.2f}s • {report['width']} × {report['height']} • "+
                            ('Shortened to available media.' if report.get('shortened') else 'Full decode passed.'))
        rhythm=report.get('music_alignment') or {}
        if str(rhythm.get('mode','')).startswith('beats') and rhythm.get('tempo_bpm'):
            self.status.setText(self.status.text()+f" Cut to a measured {rhythm['tempo_bpm']:.0f} BPM beat grid.")
        self.open_button.setEnabled(True); self.preview_file(path)
        if not replay: self.show_timeline(Timeline.load(Path(path).with_suffix('.timeline.json')))
        self.status.setText(self.status.text()+(' Preview ready — Render final when you like it.' if preview else ' Saved to '+path))

    # ---- Director chat -------------------------------------------------------------------------
    def chat_director(self):
        """The chat backend: Claude when chosen as director, otherwise the local model."""
        mode=self.director_mode.currentData()
        model=self.ai_model.text().strip() or LOCAL_MODEL
        key=('claude',None) if mode=='claude' else ('local',model)
        if self.chat_session is None or self.chat_session[0]!=key:
            from .edit_chat import EditChat
            from .vision_director import ClaudeDirector, LocalDirector
            director=ClaudeDirector() if key[0]=='claude' else LocalDirector(model,timeout=600)
            self.chat_session=(key,EditChat(director))
            self.chat_chip.setText('Claude • cloud' if key[0]=='claude' else 'On this computer')
            self.chat_chip.setObjectName('chip' if key[0]=='claude' else 'chipTeal')
            self.chat_chip.style().unpolish(self.chat_chip);self.chat_chip.style().polish(self.chat_chip)
        return key,self.chat_session[1]

    def chat_state(self):
        shots=[]
        if self.timeline is not None:
            for i,clip in enumerate(self.timeline.clips):
                moment=next((c for c in self.alternates
                             if c['source']==clip.source and clip.start<=c['time']<=clip.start+clip.duration),{})
                shots.append(dict(shot=i+1,seconds=round(clip.duration,2),slow_motion=clip.speed_profile!='normal',
                                  punch_ins=len(clip.accents),event=moment.get('event'),note=moment.get('ai_note')))
        result=None
        if self.last_report:
            rhythm=self.last_report.get('music_alignment') or {}
            result=dict(duration=self.last_report.get('duration'),on_beat=rhythm.get('on_beat'),
                        tempo_bpm=rhythm.get('tempo_bpm'),director=self.last_report.get('ai_director'))
        return dict(song=Path(self.music_path).name if self.music_path else (self.song_name.text().strip() or None),
                    gameplay_clips=self.footage.count(),length_seconds=self.duration.value(),pace=self.pace.currentData(),
                    look=self.look.currentData(),tone=self.story_tone.currentData(),tones=list(STORY_TONES),
                    closing_line=self.closing_line.text(),brief=self.ai_brief.text(),format=self.export_preset.currentData(),
                    slow_motion=self.slowmo.currentData(),swishes=self.sfx.isChecked(),motion_blur=self.motion_blur.isChecked(),
                    director=self.director_mode.currentData(),shot_count=len(shots),shots=shots[:40],
                    has_preview=self.preview_timeline is not None,last_result=result)

    def chat_bubble(self,who,text,kind='reply'):
        from html import escape
        colours={'user':('#6d4dff','#ffffff'),'reply':('#ffffff','#15131f'),'note':('#e4f7f5','#0b8a7e'),
                 'warn':('#fff4dc','#a76a00')}
        background,ink=colours[kind]
        align='right' if kind=='user' else 'left'
        width='68%' if kind in ('user','reply') else '52%'
        # Qt rich text: tables honour width/align/bgcolor/cellpadding (CSS radii are ignored).
        self.chat_log.append(f'<table width="{width}" align="{align}" bgcolor="{background}" cellpadding="8" '
                             f'cellspacing="0" style="margin-bottom:6px;"><tr><td style="color:{ink};">'
                             f'<span style="font-size:11px;font-weight:700;">{escape(who)}</span><br>{escape(text)}'
                             '</td></tr></table>')
        self.chat_log.verticalScrollBar().setValue(self.chat_log.verticalScrollBar().maximum())

    def use_suggestion(self,text):
        if '<' in text:
            self.chat_input.setText(text.split('<')[0]);self.chat_input.setFocus()
        else:
            self.chat_input.setText(text);self.send_chat()

    def send_chat(self):
        message=self.chat_input.text().strip()
        if not message or self.chat_job is not None:return
        try:
            key,session=self.chat_director()
        except Exception as error:
            self.chat_bubble('Director',str(error),'warn');return
        state=self.chat_state()
        self.chat_input.clear();self.chat_bubble('You',message,'user')
        self.chat_send.setEnabled(False);self.chat_send.setText('Thinking…')

        from .edit_chat import contact_sheet, wants_a_look
        timeline=self.timeline if wants_a_look(message) else None
        if timeline is not None:self.chat_bubble('Director','Watching your edit…','note')

        def turn():
            if key[0]=='local':
                from .local_ai import readiness
                ready,note=readiness(key[1])
                if not ready:raise ValueError(note)
            return session.ask(message,state,contact_sheet(timeline) if timeline is not None else None)
        self.chat_job=ChatJob(turn)
        self.chat_job.done.connect(self.chat_replied)
        self.chat_job.failed.connect(lambda m:self.chat_bubble('Director',m,'warn'))
        self.chat_job.finished.connect(self.chat_finished)
        self.chat_job.start()

    def chat_finished(self):
        self.chat_send.setEnabled(True);self.chat_send.setText('Send')
        self.chat_job.deleteLater();self.chat_job=None

    def chat_replied(self,result):
        self.chat_bubble('Director',result['reply'])
        for action,value,reason in result['rejected']:
            self.chat_bubble('Not applied',f'{action} “{value}”: {reason}','warn')
        self.apply_chat_actions(list(result['actions']))

    def apply_chat_actions(self,actions):
        """Apply validated chat actions through the normal controls; a song link pauses until it downloads."""
        while actions:
            action,value=actions.pop(0)
            if action=='set_music':
                self.song_name.setText(value);self.clear_music_selection()
                kind,_=interpret_song(value)
                if kind=='link':
                    self.chat_bubble('Applied',f'Fetching the song from the link…','note')
                    rest=list(actions)
                    self.add_music_link(interpret_song(value)[1],then=lambda:self.apply_chat_actions(rest))
                    return
                if not self.resolve_song():
                    self.chat_bubble('Not applied',f'Could not find the song “{value}”','warn');continue
                self.chat_bubble('Applied',f'Song → {Path(self.music_path).name}','note');continue
            note=self.apply_chat_action(action,value)
            self.chat_bubble('Applied' if note[0] else 'Not applied',note[1],'note' if note[0] else 'warn')
        self.save_preferences()

    def apply_chat_action(self,action,value):
        def choose(combo,data,name):
            index=combo.findData(data)
            if index<0:return False,f'{name}: “{value}” is not available'
            combo.setCurrentIndex(index);return True,f'{name} → {combo.currentText()}'
        if action=='set_pace':return choose(self.pace,value,'Pace')
        if action=='set_look':return choose(self.look,value,'Look')
        if action=='set_tone':return choose(self.story_tone,value,'Story tone')
        if action=='set_format':return choose(self.export_preset,value,'Export')
        if action=='set_slow_motion':return choose(self.slowmo,value,'Slow motion')
        if action=='set_length':
            self.duration.setValue(float(value));return True,f'Length → {self.duration.value():g} s'
        if action=='set_closing_line':
            self.closing_line.setText(value);return True,f'Closing line → “{value}”' if value else 'Closing line removed'
        if action=='set_brief':
            self.ai_brief.setText(value);return True,f'Brief → {value}'
        if action in ('set_swishes','set_motion_blur'):
            box=self.sfx if action=='set_swishes' else self.motion_blur
            box.setChecked(value=='on');return True,f'{box.text()} → {value}'
        if action in ('move_shot','swap_shot'):
            if self.timeline is None:return False,'Create a montage first'
            row=int(value.split()[0].replace('shot',''))-1
            if not 0<=row<len(self.timeline.clips):return False,'No such shot'
            self.timeline_table.selectRow(row)
            if action=='move_shot':
                step=-1 if value.endswith('earlier') else 1
                if not 0<=row+step<len(self.timeline.clips):return False,'Shot is already at that end'
                try:edited=exchange_shots(self.timeline,row,row+step)
                except ValueError as error:return False,str(error)
                self.show_timeline(edited);self.timeline_table.selectRow(row+step)
                return True,f'Moved shot {row+1} {value.split()[-1]} • Render loaded timeline to see it'
            used=lambda c:any(o.source==c['source'] and o.start<=c['time']<=o.start+o.duration for o in self.timeline.clips)
            for option in sorted((c for c in self.alternates if not used(c)),key=lambda c:-c['score'])[:5]:
                edited,applied,rejected=swap_shots(self.timeline,[(row,option)])
                if applied:
                    self.show_timeline(edited);self.timeline_table.selectRow(row)
                    return True,f'Swapped shot {row+1} for an unused moment (score {option["score"]:.2f}) • Render loaded timeline to see it'
            return False,'No unused moment fits that shot'
        if action=='make':
            if self.job is not None:return False,'A job is already running'
            if value=='final':self.finalize_preview()
            else:self.export(automatic=True,preview=value=='preview')
            return True,{'preview':'Making a quick preview','montage':'Creating the montage','final':'Rendering the final from the preview'}[value]
        return False,f'Unknown action {action}'

    def export_formats(self):
        """Render the loaded edit for every platform format in the background."""
        if self.job is not None or self.timeline is None:return
        from .pipeline import render_formats
        movies=QStandardPaths.writableLocation(QStandardPaths.MoviesLocation) or str(Path.home()/'Videos')
        base=Path(movies)/'DRIFT'/(datetime.now().strftime('montage-%Y%m%d-%H%M%S-')+uuid4().hex[:6]+'.mp4')
        timeline=self.timeline
        self.create_button.setEnabled(False);self.formats_button.setEnabled(False)
        self.progress.setRange(0,1000);self.progress.setValue(0)
        self.job=RenderJob(lambda:render_formats(timeline,base))
        self.job.done.connect(self.formats_done)
        self.job.failed.connect(self.failed)
        self.job.finished.connect(self.finished)
        self.job.progress.connect(self.on_progress)
        self.cancel_button.setEnabled(True)
        self.job.start()

    def formats_done(self,reports):
        self.last_output=reports[-1]['path'];self.open_button.setEnabled(True)
        self.status.setText('Delivered '+' • '.join(f"{r['format']} {r['width']}×{r['height']}" for r in reports)+
                            ' • all fully decoded')
        self.preview_file(reports[0]['path'])

    def finalize_preview(self):
        if self.preview_timeline is None:return
        try:
            draft=Timeline.load(self.preview_timeline)
            final=retarget(draft,self.delivery_settings(),interpolation=self.slowmo.currentData())
        except Exception as error:
            QMessageBox.warning(self,'Cannot finalise preview',str(error));return
        self.export(timeline=final)

    def selected_shot(self):
        row=self.timeline_table.currentRow()
        return row if self.timeline is not None and 0<=row<len(self.timeline.clips) else None

    def move_selected(self,step):
        row=self.selected_shot()
        if row is None or not 0<=row+step<len(self.timeline.clips):return
        try:
            edited=exchange_shots(self.timeline,row,row+step)
        except ValueError as error:
            QMessageBox.information(self,'Cannot move shot',str(error));return
        self.show_timeline(edited);self.timeline_table.selectRow(row+step)
        self.status.setText(f'Moved shot {row+1} • Render loaded timeline to see the edit.')

    def swap_selected(self):
        row=self.selected_shot()
        if row is None:return
        used=lambda c:any(o.source==c['source'] and o.start<=c['time']<=o.start+o.duration for o in self.timeline.clips)
        options=sorted((c for c in self.alternates if not used(c)),key=lambda c:-c['score'])[:30]
        if not options:
            QMessageBox.information(self,'No alternates','Generate a montage first; unused analysed moments appear here.');return
        names=[f"{Path(c['source']).name} @ {c['time']:.1f}s • score {c['score']:.2f}"+(f" • {c['event']}" if c.get('event') else '')
               for c in options]
        choice,ok=QInputDialog.getItem(self,'Swap shot',f'Replace shot {row+1} with:',names,0,False)
        if not ok:return
        edited,applied,rejected=swap_shots(self.timeline,[(row,options[names.index(choice)])])
        if rejected:
            QMessageBox.information(self,'Cannot swap',rejected[0]['reason']);return
        self.show_timeline(edited);self.timeline_table.selectRow(row)
        self.status.setText(f'Swapped shot {row+1} • Render loaded timeline to see the edit.')

    def on_progress(self,fraction,message):
        self.progress.setRange(0,1000);self.progress.setValue(int(fraction*1000))
        self.status.setText(f'{message} • {fraction*100:.0f}%')

    def cancel_job(self):
        if self.job is not None:
            self.job.cancel.set();self.cancel_button.setEnabled(False)
            self.status.setText('Cancelling…')

    def failed(self,message):
        if message==CANCELLED:
            self.status.setText('Cancelled • nothing was saved.');return
        self.status.setText('Export failed • '+message)
        QMessageBox.warning(self,'Export failed',message)

    def finished(self):
        self.progress.setRange(0,1); self.progress.setValue(1)
        self.create_button.setEnabled(True);self.create_button.setText('Create montage')
        self.export_button.setEnabled(True); self.replay_button.setEnabled(self.timeline is not None)
        self.formats_button.setEnabled(self.timeline is not None)
        self.cancel_button.setEnabled(False)
        self.job.deleteLater(); self.job=None

    def open_export(self):
        if self.last_output: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.last_output).parent)))

    def closeEvent(self,event):
        if self.job is not None:
            answer=QMessageBox.question(self,'Job in progress','Cancel the current job and close?')
            if answer==QMessageBox.Yes:
                self.job.cancel.set();self.job.wait(30000);event.accept()
            else:event.ignore()
        else: event.accept()


def self_check():
    """Packaged-build smoke test: fonts, resources, FFmpeg discovery and the window itself."""
    from PySide6.QtGui import QFontDatabase
    from .environment import detect_environment
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setStyleSheet(STYLE)
    window=Studio(QSettings(str(Path(QStandardPaths.writableLocation(QStandardPaths.TempLocation))/'drift-self-check.ini'),
                            QSettings.IniFormat))
    environment=detect_environment()
    result=dict(window=not window.grab().isNull(),fonts=all(f in QFontDatabase.families() for f in ('Manrope','Sora')),
                banner_art=not window.banner.art.isNull(),swishes=len(__import__('montage_editor.craft',fromlist=['x']).SWISHES),
                ffmpeg=environment['ffmpeg'],ffprobe=environment['ffprobe'])
    window.close()
    print(json.dumps(result))
    return 0 if result['window'] and result['fonts'] and result['banner_art'] and result['swishes'] else 1


def main():
    if '--self-check' in sys.argv:
        sys.exit(self_check())
    app=QApplication(sys.argv); app.setStyleSheet(STYLE)
    window=Studio(); window.show(); sys.exit(app.exec())


if __name__ == '__main__':
    main()
