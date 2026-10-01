"""Desktop workspace connected to the real local montage engine."""
import json
from pathlib import Path
import sys
from datetime import datetime
from uuid import uuid4

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSettings, QStandardPaths
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QListWidget, QFormLayout, QSpinBox, QDoubleSpinBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QProgressBar,
    QMessageBox, QSlider, QFrame, QStackedWidget, QGraphicsDropShadowEffect, QLineEdit, QScrollArea, QInputDialog)

from .workspace_widgets import CinemaCanvas, TimelineLanes, CathedralBanner
from .music_library import find_songs, AUDIO, VIDEO
from .config import Settings
from .pipeline import Timeline, create_montage, render, probe, analyze_gameplay

STYLE = '''
QWidget { background:#0d0e10; color:#ededee; font-family:Inter,Segoe UI,sans-serif; font-size:12px; }
QMainWindow {background:#090a0c;} QFrame#panel {background:qlineargradient(x1:0,y1:0,x2:0.8,y2:1,stop:0 #242831,stop:0.15 #171b22,stop:1 #101319);border:1px solid #343a45;border-radius:14px;}
QLabel {background:transparent;} QLabel#brand {font-size:23px;font-weight:700;letter-spacing:3px;}
QLabel#title {font-size:20px;font-weight:600;} QLabel#muted {color:#979ba4;}
QLabel#eyebrow {color:#c9ced5;font-size:10px;font-weight:600;letter-spacing:2px;}
QPushButton {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #303640,stop:1 #1b2029);border:1px solid #424955;border-radius:7px;padding:9px 13px;}
QPushButton:hover {background:#30333b;border-color:#777b86;}
QPushButton:disabled {color:#60636c;background:#191b20;}
QPushButton#primary {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #9ba3ae);color:#151311;font-weight:700;border:0;padding:12px;}
QListWidget,QTableWidget {background:#111216;border:1px solid #2a2d34;border-radius:6px;alternate-background-color:#181a20;}
QHeaderView::section {background:#202228;color:#aeb2bc;border:0;padding:7px;}
QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox {background:#202228;border:1px solid #343740;border-radius:5px;padding:6px;}
QProgressBar {border:0;background:#22252b;border-radius:3px;height:5px;}
QProgressBar::chunk {background:#c9ced5;}
QSlider::groove:horizontal {height:4px;background:#30333b;}
QSlider::handle:horizontal {background:#edf0f4;width:10px;margin:-4px 0;border-radius:5px;}
QFrame#rail {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #101318,stop:1 #050608);border-right:1px solid #353b44;}
QPushButton#nav {text-align:left;background:transparent;border:0;padding:12px;font-size:14px;}
QPushButton#nav:hover {background:#2a3038;border:1px solid #aeb4be;}
QPushButton#workflow {border:1px solid #787f8a;font-size:12px;text-align:left;padding:12px;}
QSplitter::handle {background:#0d0e10;width:8px;height:8px;}
'''


def label(text, kind=None):
    item = QLabel(text)
    if kind:
        item.setObjectName(kind)
    return item


def panel():
    frame = QFrame()
    frame.setObjectName('panel')
    shadow = QGraphicsDropShadowEffect(frame)
    shadow.setBlurRadius(22); shadow.setOffset(0,6); shadow.setColor(QColor(0,0,0,150))
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
        self.resize(1680,1120)
        self.setMinimumSize(1280,950)
        self.music_path = None
        self.timeline = None
        self.last_output = None
        self.job = None
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0,0,16,14); outer.setSpacing(16)
        rail=QFrame(); rail.setObjectName('rail'); rail.setFixedWidth(190)
        rail_layout=QVBoxLayout(rail); rail_layout.setContentsMargins(18,24,18,20); rail_layout.setSpacing(10)
        rail_layout.addWidget(label('✝  DRIFT','brand'))
        rail_layout.addWidget(label('MONTAGE STUDIO','eyebrow'))
        rail_layout.addSpacing(22)
        for name,callback in [('Home',lambda:self.screen.setCurrentIndex(0)),
                              ('Import',self.import_media),('AI Director',lambda:self.show_advanced(self.ai_model)),
                              ('Timeline',lambda:self.timeline_table.setFocus()),
                              ('Effects',lambda:self.show_advanced(self.transition)),
                              ('Audio',self.import_music),('Color',None),('Styles',None),
                              ('Export',self.export)]:
            button=QPushButton(name);button.setObjectName('nav')
            if callback:button.clicked.connect(callback)
            else:button.setEnabled(False);button.setToolTip('Planned — not yet implemented')
            rail_layout.addWidget(button)
        rail_layout.addStretch()
        rail_layout.addWidget(label('PROJECT','eyebrow'))
        rail_layout.addWidget(label('Local workspace','muted'))
        rail_layout.addWidget(label('FAITH • FOCUS','eyebrow'))
        outer.addWidget(rail)
        body=QWidget(); outer.addWidget(body,1)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0,18,0,0)
        header = QHBoxLayout()
        header.addWidget(label('D R I F T', 'brand'))
        header.addWidget(label(' /  MONTAGE STUDIO', 'muted'))
        header.addStretch()
        header.addWidget(label('PURPOSE IN EVERY FRAME', 'eyebrow'))
        layout.addLayout(header)
        subtitle = label('Create with conviction.   •   Local footage. Real exports.', 'muted')
        layout.addWidget(subtitle)
        self.banner=CathedralBanner(); layout.addWidget(self.banner)
        steps=QHBoxLayout(); steps.setSpacing(12)
        for title,detail,callback in [('IMPORT','Clips · Recordings · Music',self.import_media),
                                      ('ANALYZE','Measure motion and audio',self.analyze_sources),
                                      ('GENERATE','Build and render your edit',self.export),
                                      ('REVIEW','Open a saved timeline',self.load_timeline),
                                      ('EXPORT','Render the loaded timeline',self.replay_export)]:
            card=QPushButton(title+'  →\n'+detail); card.setObjectName('workflow')
            card.setMinimumHeight(68);card.clicked.connect(callback);steps.addWidget(card,1)
        self.steps_widget=QWidget();self.steps_widget.setLayout(steps);self.steps_widget.hide()
        layout.addWidget(self.steps_widget)
        intake,intake_layout=panel()
        intake_layout.addWidget(label('DROP CLIPS. CHOOSE A SONG. CREATE.', 'eyebrow'))
        self.drop_hint=label('Drop gameplay clips anywhere in this window — or use Import.', 'muted')
        intake_layout.addWidget(self.drop_hint)
        quick=QHBoxLayout()
        self.song_name=QLineEdit();self.song_name.setPlaceholderText('Type the song title from your music folder…')
        self.song_name.textEdited.connect(lambda:self.clear_music_selection())
        quick.addWidget(self.song_name,1)
        library=QPushButton('Music folder');library.clicked.connect(self.choose_music_folder);quick.addWidget(library)
        self.create_button=QPushButton('Create Christian montage');self.create_button.setObjectName('primary')
        self.create_button.clicked.connect(lambda:self.export(automatic=True));quick.addWidget(self.create_button)
        advanced=QPushButton('Advanced');advanced.clicked.connect(self.toggle_advanced);quick.addWidget(advanced)
        intake_layout.addLayout(quick);layout.addWidget(intake)

        workspace = QSplitter(Qt.Horizontal)
        layout.addWidget(workspace,1)
        assets,left = panel()
        left.addWidget(label('01  /  SOURCE LIBRARY','eyebrow'))
        left.addWidget(label('Your footage','title'))
        self.footage = QListWidget()
        left.addWidget(self.footage,1)
        self.import_button = QPushButton('+ Import gameplay')
        self.import_button.clicked.connect(self.import_media)
        left.addWidget(self.import_button)
        remove = QPushButton('Remove selected')
        remove.clicked.connect(lambda: self.footage.takeItem(self.footage.currentRow()))
        left.addWidget(remove)
        self.music_label = label('No music selected','muted')
        self.music_label.setWordWrap(True)
        left.addWidget(self.music_label)
        music = QPushButton('Choose music track')
        music.clicked.connect(self.import_music)
        left.addWidget(music)
        load = QPushButton('Open saved timeline')
        load.clicked.connect(self.load_timeline)
        left.addWidget(load)
        self.assets_panel=assets
        workspace.addWidget(assets)
        assets.hide()
        center = QWidget()
        column = QVBoxLayout(center)
        column.setContentsMargins(0,0,0,0)
        preview,view = panel()
        view.addWidget(label('02  /  SCREENING ROOM','eyebrow'))
        self.preview_title = label('Import footage to begin','title')
        view.addWidget(self.preview_title)
        self.video = QVideoWidget()
        self.video.setMinimumHeight(210)
        self.screen = QStackedWidget()
        empty = CinemaCanvas(); empty_layout = QVBoxLayout(empty)
        empty_layout.addStretch(3)
        message = label('YOUR NEXT STORY STARTS HERE', 'eyebrow')
        message.setAlignment(Qt.AlignCenter); empty_layout.addWidget(message)
        message = label('From the struggle. Into the light.', 'title')
        message.setAlignment(Qt.AlignCenter); empty_layout.addWidget(message)
        message = label('Import gameplay, choose a track, then shape the message.', 'muted')
        message.setAlignment(Qt.AlignCenter); empty_layout.addWidget(message)
        empty_layout.addStretch(1)
        self.screen.addWidget(empty); self.screen.addWidget(self.video)
        view.addWidget(self.screen,1)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        controls = QHBoxLayout()
        play = QPushButton('Play / Pause')
        play.clicked.connect(self.toggle_play)
        controls.addWidget(play)
        self.scrub = QSlider(Qt.Horizontal)
        self.scrub.sliderMoved.connect(self.player.setPosition)
        self.player.positionChanged.connect(self.scrub.setValue)
        self.player.durationChanged.connect(lambda duration:self.scrub.setRange(0,duration))
        controls.addWidget(self.scrub,1)
        self.clock = label('00:00','muted')
        self.player.positionChanged.connect(lambda t:self.clock.setText(f'{t//60000:02d}:{t//1000%60:02d}'))
        controls.addWidget(self.clock)
        view.addLayout(controls)
        column.addWidget(preview,3)
        timeline,track = panel()
        track.addWidget(label('03  /  EDIT TIMELINE','eyebrow'))
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
        track.addWidget(label('Populated from a generated or loaded timeline. Manual clip editing is planned.','muted'))
        column.addWidget(timeline,2)
        workspace.addWidget(center)
        inspector,right = panel()
        right.addWidget(label('04  /  SCENE & STORY','eyebrow'))
        right.addWidget(label('Faith drives discipline.','title'))
        self.analysis_label=label('SCENE ANALYSIS\nImport footage and choose Analyze.\nMotion/audio scores are heuristic; kill detection is planned.','muted')
        self.analysis_label.setWordWrap(True);right.addWidget(self.analysis_label)
        right.addWidget(label('Layer your own Christian narration or reference audio.','muted'))
        self.dialogue = QTableWidget(0,6)
        self.dialogue.setHorizontalHeaderLabels(['Audio','At','In','Length','Reference','Kind'])
        self.dialogue.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.dialogue.setMinimumHeight(100)
        self.dialogue.setToolTip('Editable timing in seconds. Reference is metadata, not a rendered caption.')
        right.addWidget(self.dialogue)
        add = QPushButton('+ Add dialogue recording')
        add.clicked.connect(self.add_dialogue)
        right.addWidget(add)
        delete = QPushButton('Remove selected dialogue')
        delete.clicked.connect(lambda:self.dialogue.removeRow(self.dialogue.currentRow()))
        right.addWidget(delete)
        form = QFormLayout()
        self.director_mode=QComboBox()
        self.director_mode.addItems(['Automatic • activity engine','Automatic • Ollama (experimental)'])
        form.addRow('Director',self.director_mode)
        self.ai_model=QLineEdit();self.ai_model.setPlaceholderText('Installed Ollama model name')
        self.ai_model.setEnabled(False)
        self.director_mode.currentIndexChanged.connect(lambda i:self.ai_model.setEnabled(i==1))
        form.addRow('Local model',self.ai_model)
        self.ai_brief=QLineEdit();self.ai_brief.setPlaceholderText('Cinematic Christian hope and perseverance')
        form.addRow('Creative brief',self.ai_brief)

        self.transition = QComboBox()
        for title,key in [('Hard cut','cut'),('Fade through black','fade_black'),('Fade through white','fade_white')]:
            self.transition.addItem(title,key)
        form.addRow('Transition',self.transition)
        self.fade = QDoubleSpinBox(); self.fade.setRange(.05,1); self.fade.setSingleStep(.05); self.fade.setValue(.2)
        form.addRow('Fade seconds',self.fade)
        self.duration = QDoubleSpinBox(); self.duration.setRange(1,3600); self.duration.setValue(30)
        form.addRow('Target seconds',self.duration)
        self.resolution = QComboBox()
        for title,size in [('HD • 1280 × 720',(1280,720)),('Full HD • 1920 × 1080',(1920,1080)),('Portrait • 1080 × 1920',(1080,1920))]:
            self.resolution.addItem(title,size)
        form.addRow('Canvas',self.resolution)
        self.fps = QSpinBox(); self.fps.setRange(1,120); self.fps.setValue(30)
        form.addRow('Frames / second',self.fps)
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
        inspector_scroll.setMinimumWidth(360);workspace.addWidget(inspector_scroll)
        self.inspector_scroll=inspector_scroll;inspector_scroll.hide()
        workspace.setSizes([220,1000,400])
        self.progress = QProgressBar(); self.progress.setRange(0,1); self.progress.setValue(0); self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.status = label('Ready • Import gameplay and music. Advanced AI direction and speed ramps are planned.','muted')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        self.footage.currentTextChanged.connect(self.preview_file)
        self.player.errorOccurred.connect(lambda error,message:self.status.setText('Preview: '+message))
        self.ai_model.setText(str(self.preferences.value('ai_model','')))
        saved_mode=int(self.preferences.value('director_mode',0))
        self.director_mode.setCurrentIndex(saved_mode if saved_mode in (0,1) else 0)
        self.ai_brief.setText(str(self.preferences.value('brief','')))
        self.ai_model.editingFinished.connect(self.save_preferences)
        self.director_mode.currentIndexChanged.connect(self.save_preferences)
        self.ai_brief.editingFinished.connect(self.save_preferences)
        self.status.setText('Drop clips, type your song, and create. Christian direction is the default. Set local AI once in Advanced.')

    def save_preferences(self,*args):
        for key,value in [('music_folder',self.music_folder),('ai_model',self.ai_model.text().strip()),
                          ('director_mode',self.director_mode.currentIndex()),('brief',self.ai_brief.text().strip())]:
            self.preferences.setValue(key,value)

    def show_advanced(self,target=None):
        self.inspector_scroll.show();self.steps_widget.show()
        if target is not None:target.setFocus();self.inspector_scroll.ensureWidgetVisible(target)

    def toggle_advanced(self):
        visible=self.inspector_scroll.isHidden()
        self.inspector_scroll.setVisible(visible);self.steps_widget.setVisible(visible)

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
            self.assets_panel.show();self.footage.setCurrentRow(0)
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
        ranked=sorted(candidates,key=lambda c:-c['score'])
        if ranked:
            top=ranked[0]
            self.analysis_label.setText(f"SCENE ANALYSIS\n{len(ranked)} candidate moments\nTop activity: {top['score']:.3f} (not confidence)\n{Path(top['source']).name} at {top['time']:.2f}s\nSemantic game-event detection is planned.")
        self.status.setText(f'Analysis complete • {len(ranked)} motion/audio candidate moments. Ready to generate.')

    def import_media(self):
        files,_ = QFileDialog.getOpenFileNames(self,'Import gameplay','','Video (*.mp4 *.mkv *.mov *.webm);;All files (*)')
        self.add_files(files)

    def import_music(self):
        path,_ = QFileDialog.getOpenFileName(self,'Choose music','','Audio (*.wav *.mp3 *.flac *.m4a);;All files (*)')
        if path: self.select_music(path)

    def preview_file(self,path):
        if path:
            self.screen.setCurrentIndex(1)
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
        return dict(dialogue=cues,transition=self.transition.currentData(),transition_duration=self.fade.value())

    def show_timeline(self,timeline):
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
                settings=Settings(width=width,height=height,fps=self.fps.value(),duration=self.duration.value())
                sources=[self.footage.item(i).text() for i in range(self.footage.count())]
                song=self.music_path; story=self.story()
                if automatic:story['faith_message']='Walk with Christ.'
                model=self.ai_model.text().strip() if self.director_mode.currentIndex()==1 else None
                if self.director_mode.currentIndex()==1 and not model: raise ValueError('Enter an installed local Ollama model name')
                brief=self.ai_brief.text().strip() or None
                operation=lambda:create_montage(sources,song,path,settings,story,model,brief)
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
        self.open_button.setEnabled(True); self.preview_file(path)
        if not replay: self.show_timeline(Timeline.load(Path(path).with_suffix('.timeline.json')))
        self.status.setText(self.status.text()+' Saved to '+path)

    def failed(self,message):
        self.status.setText('Export failed • '+message)
        QMessageBox.warning(self,'Export failed',message)

    def finished(self):
        self.progress.setRange(0,1); self.progress.setValue(1)
        self.create_button.setEnabled(True);self.create_button.setText('Create Christian montage')
        self.export_button.setEnabled(True); self.replay_button.setEnabled(self.timeline is not None)
        self.job.deleteLater(); self.job=None

    def open_export(self):
        if self.last_output: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.last_output).parent)))

    def closeEvent(self,event):
        if self.job is not None:
            QMessageBox.information(self,'Export in progress','Wait for the current export before closing.'); event.ignore()
        else: event.accept()


def main():
    app=QApplication(sys.argv); app.setStyleSheet(STYLE)
    window=Studio(); window.show(); sys.exit(app.exec())


if __name__ == '__main__':
    main()
