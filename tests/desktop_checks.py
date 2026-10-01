"""Run explicitly in the desktop CI job with QT_QPA_PLATFORM=offscreen."""
import unittest
from pathlib import Path
import tempfile
from PySide6.QtCore import QSettings
from montage_editor.desktop import QApplication, Studio, STYLE, QTableWidgetItem, RenderJob
from montage_editor.pipeline import Timeline, Clip
from montage_editor.config import Settings


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def test_real_timeline_and_story_controls(self):
        window=Studio()
        window.show_timeline(Timeline(1,'song',Settings().__dict__,[Clip('source.mp4',1,3,.7)]))
        self.assertEqual(window.timeline_table.item(0,1).text(),'1.00s')
        self.assertTrue(window.replay_button.isEnabled())
        window.dialogue.insertRow(0)
        for i,value in enumerate(['voice.wav','1','0','2','John 14:6 / user recording','quotation']):
            window.dialogue.setItem(0,i,QTableWidgetItem(value))
        self.assertEqual(window.story()['dialogue'][0]['text_kind'],'quotation')
        self.assertEqual(window.story()['dialogue'][0]['at'],1)
        window.close()

    def test_reference_workspace_and_real_analysis(self):
        window=Studio()
        self.assertFalse(window.banner.art.isNull())
        window.show_analysis([dict(source='source.mp4',time=2.5,score=.8)])
        self.assertIn('0.800 (not confidence)',window.analysis_label.text())
        window.show(); self.app.processEvents()
        self.assertFalse(window.grab().isNull())
        window.close()

    def test_drop_ingestion_and_saved_setup(self):
        with tempfile.TemporaryDirectory() as d:
            prefs=QSettings(str(Path(d)/'prefs.ini'),QSettings.IniFormat)
            window=Studio(prefs)
            video=Path(d)/'clip.mp4';song=Path(d)/'Artist - Hope.wav'
            video.touch();song.touch()
            window.add_files([str(video),str(video),str(song)])
            self.assertEqual(window.footage.count(),1)
            self.assertEqual(window.music_path,str(song.resolve()))
            window.ai_model.setText('local-model');window.director_mode.setCurrentIndex(1)
            window.music_folder=d;window.save_preferences();window.close()
            restored=Studio(prefs)
            self.assertEqual(restored.ai_model.text(),'local-model')
            self.assertEqual(restored.director_mode.currentIndex(),1)
            self.assertEqual(restored.music_folder,d)
            self.assertTrue(restored.inspector_scroll.isHidden())
            restored.close()

    def test_background_job_reports_failures(self):
        errors=[]
        def fail(): raise ValueError('invalid media')
        job=RenderJob(fail)
        job.failed.connect(errors.append)
        job.start(); self.assertTrue(job.wait(5000)); self.app.processEvents()
        self.assertEqual(errors,['invalid media'])
