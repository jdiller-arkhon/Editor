"""Desktop workspace connected to the real local montage engine."""
import json
import numpy as np
from pathlib import Path
import sys
from datetime import datetime
from uuid import uuid4

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSettings, QStandardPaths
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QFileDialog, QListWidget, QFormLayout, QSpinBox, QDoubleSpinBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QProgressBar,
    QMessageBox, QSlider, QFrame, QStackedWidget, QGraphicsDropShadowEffect, QLineEdit, QScrollArea, QInputDialog)

from .workspace_widgets import BrandMark, CinemaCanvas, TimelineLanes, CathedralBanner
from .music_library import find_songs, AUDIO, VIDEO
from .config import Settings
from .pipeline import Timeline, create_montage, render, probe, analyze_gameplay

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


class RenderJob(QThread):
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
        self.song_name=QLineEdit();self.song_name.setPlaceholderText('Type a song title from your music folder…')
        self.song_name.textEdited.connect(lambda:self.clear_music_selection())
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
        self.create_button=QPushButton('Create montage');self.create_button.setObjectName('primary')
        self.create_button.clicked.connect(lambda:self.export(automatic=True))
        intake_layout.addWidget(self.create_button)
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
        track.addWidget(label('Built from the generated or loaded timeline. Manual clip editing is planned.','muted'))
        column.addWidget(timeline)
        self.progress = QProgressBar(); self.progress.setRange(0,1); self.progress.setValue(0); self.progress.setTextVisible(False)
        column.addWidget(self.progress)
        self.status = label('Ready for your footage.','status')
        self.status.setWordWrap(True); column.addWidget(self.status)
        column.addStretch()
        main.setMinimumHeight(main.sizeHint().height())
        workspace.addWidget(main)
        inspector,right = panel()
        right.addWidget(step(4,'Creative controls'))
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
        self.director_mode.addItems(['Automatic • activity engine','Automatic • Ollama (experimental)',
                                     'Automatic • Claude vision editor'])
        form.addRow('Director',self.director_mode)
        self.director_note=QLabel('Claude reviews sampled frames of your footage to pick highlights. '
                                  'Frames are sent to Anthropic; needs ANTHROPIC_API_KEY or ant auth login.')
        self.director_note.setWordWrap(True)
        self.director_note.setVisible(False)
        self.director_mode.currentIndexChanged.connect(lambda i:self.director_note.setVisible(i==2))
        form.addRow(self.director_note)
        self.ai_model=QLineEdit();self.ai_model.setPlaceholderText('Installed Ollama model name')
        self.ai_model.setEnabled(False)
        self.director_mode.currentIndexChanged.connect(lambda i:self.ai_model.setEnabled(i==1))
        form.addRow('Local model',self.ai_model)
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
        self.ai_model.setText(str(self.preferences.value('ai_model','')))
        saved_mode=int(self.preferences.value('director_mode',0))
        self.director_mode.setCurrentIndex(saved_mode if saved_mode in (0,1,2) else 0)
        self.ai_brief.setText(str(self.preferences.value('brief','')))
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
        for key,value in [('music_folder',self.music_folder),('ai_model',self.ai_model.text().strip()),
                          ('director_mode',self.director_mode.currentIndex()),('brief',self.ai_brief.text().strip()),
                          ('story_tone',self.story_tone.currentData()),('closing_line',self.closing_line.text())]:
            self.preferences.setValue(key,value)

    def update_story_tone(self,*args):
        defaults={values[1] for values in STORY_TONES.values()}
        if self.closing_line.text() in defaults:
            self.closing_line.setText(STORY_TONES[self.story_tone.currentData()][1])
        self.save_preferences()

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

    def resolve_song(self):
        if self.music_path and Path(self.music_path).is_file():return True
        try:
            if not self.music_folder:
                self.choose_music_folder()
                if not self.music_folder:return False
            matches=find_songs(self.music_folder,self.song_name.text())
            if not matches:
                QMessageBox.information(self,'Song not found','No matching local audio. Try artist and title, choose another folder, or drop the song file.');return False
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
        path,_ = QFileDialog.getOpenFileName(self,'Choose music','','Audio (*.wav *.mp3 *.flac *.m4a *.ogg *.opus *.aac);;All files (*)')
        if path: self.select_music(path)

    def add_music_link(self,link=None):
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
        if not self.music_folder or not Path(self.music_folder).is_dir():
            self.choose_music_folder()
            if not self.music_folder:return
        folder=self.music_folder
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
                   faith_message=self.closing_line.text().strip())
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
            except Exception as error: QMessageBox.warning(self,'Cannot load timeline',str(error))

    def export(self,checked=False,replay=False,automatic=False):
        if self.job is not None: return
        if not replay and not self.footage.count():
            QMessageBox.information(self,'Add your clips','Drop gameplay clips into the window first.');return
        if not replay and not self.resolve_song():return
        if automatic:
            movies=QStandardPaths.writableLocation(QStandardPaths.MoviesLocation) or str(Path.home()/'Videos')
            path=str(Path(movies)/'DRIFT'/(datetime.now().strftime('montage-%Y%m%d-%H%M%S-')+uuid4().hex[:6]+'.mp4'))
        else:
            path,_=QFileDialog.getSaveFileName(self,'Export montage','','MP4 (*.mp4)')
        if not path: return
        if not path.lower().endswith('.mp4'): path+='.mp4'
        try:
            if replay:
                timeline=self.timeline
                operation=lambda:render(timeline,path)
            else:
                width,height=self.resolution.currentData()
                settings=Settings(width=width,height=height,fps=self.fps.value(),duration=self.duration.value(),quality=self.quality.currentData())
                sources=[self.footage.item(i).text() for i in range(self.footage.count())]
                song=self.music_path; story=self.story()
                if automatic:
                    story.update(faith_message=self.closing_line.text().strip(),edit_profile='cinematic',
                                 gameplay_gain=.25,music_gain=.8,normalize_audio=True,transition='cinematic',
                                 auto_music_section=self.auto_music_section.isChecked())
                model=self.ai_model.text().strip() if self.director_mode.currentIndex()==1 else None
                if self.director_mode.currentIndex()==1 and not model: raise ValueError('Enter an installed local Ollama model name')
                brief=self.ai_brief.text().strip() or STORY_TONES[self.story_tone.currentData()][2]
                editor=None
                if self.director_mode.currentIndex()==2:
                    from .vision_director import ClaudeDirector
                    editor=ClaudeDirector()
                operation=lambda:create_montage(sources,song,path,settings,story,model,brief,ai_editor=editor)
        except Exception as error:
            QMessageBox.warning(self,'Check story settings',str(error)); return
        self.create_button.setEnabled(False);self.create_button.setText('Creating your montage…')
        self.export_button.setEnabled(False); self.replay_button.setEnabled(False)
        self.progress.setRange(0,0); self.status.setText('Analyzing and rendering • The workspace stays responsive. Please wait for validation.')
        self.job=RenderJob(operation)
        self.job.done.connect(lambda report:self.completed(report,path,replay))
        self.job.failed.connect(self.failed)
        self.job.finished.connect(self.finished)
        self.job.start()

    def completed(self,report,path,replay):
        self.last_output=path
        self.save_preferences()
        self.status.setText(f"Validated export • {report['duration']:.2f}s • {report['width']} × {report['height']} • "+
                            ('Shortened to available media.' if report.get('shortened') else 'Full decode passed.'))
        rhythm=report.get('music_alignment') or {}
        if rhythm.get('mode')=='beats' and rhythm.get('tempo_bpm'):
            self.status.setText(self.status.text()+f" Cut to a measured {rhythm['tempo_bpm']:.0f} BPM beat grid.")
        self.open_button.setEnabled(True); self.preview_file(path)
        if not replay: self.show_timeline(Timeline.load(Path(path).with_suffix('.timeline.json')))
        self.status.setText(self.status.text()+' Saved to '+path)

    def failed(self,message):
        self.status.setText('Export failed • '+message)
        QMessageBox.warning(self,'Export failed',message)

    def finished(self):
        self.progress.setRange(0,1); self.progress.setValue(1)
        self.create_button.setEnabled(True);self.create_button.setText('Create montage')
        self.export_button.setEnabled(True); self.replay_button.setEnabled(self.timeline is not None)
        self.job.deleteLater(); self.job=None

    def open_export(self):
        if self.last_output: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.last_output).parent)))

    def closeEvent(self,event):
        if self.job is not None:
            QMessageBox.information(self,'Job in progress','Wait for the current job before closing.'); event.ignore()
        else: event.accept()


def main():
    app=QApplication(sys.argv); app.setStyleSheet(STYLE)
    window=Studio(); window.show(); sys.exit(app.exec())


if __name__ == '__main__':
    main()
