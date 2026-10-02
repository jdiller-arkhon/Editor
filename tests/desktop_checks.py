"""Run explicitly in the desktop CI job with QT_QPA_PLATFORM=offscreen."""
import unittest
from unittest.mock import patch
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

    def test_completed_export_reports_measured_beat_grid_only_when_used(self):
        window=Studio()
        with patch.object(Studio,'save_preferences'):
            base=dict(duration=10,width=1920,height=1080,shortened=False)
            window.completed(dict(base,music_alignment=dict(mode='beats',tempo_bpm=127.6)),'out.mp4',True)
            self.assertIn('measured 128 BPM beat grid',window.status.text())
            window.completed(dict(base,music_alignment=dict(mode='attacks',tempo_bpm=129.5)),'out.mp4',True)
            self.assertNotIn('BPM',window.status.text())
        window.close()

    def test_bundled_fonts_and_white_colour_theme_load(self):
        from PySide6.QtGui import QFontDatabase
        window=Studio()
        families=QFontDatabase.families()
        self.assertIn('Manrope',families); self.assertIn('Sora',families)
        self.assertIn('background:#ffffff',STYLE.replace(' ',''))
        self.assertIn('#6d4dff',STYLE)
        self.assertNotIn('CHEVRON',STYLE)
        self.assertTrue(Path(STYLE.split('image:url(')[1].split(')')[0]).is_file())
        window.show(); self.app.processEvents()
        image=window.grab().toImage()
        corner=image.pixelColor(image.width()-40,image.height()//2)
        self.assertGreater(min(corner.red(),corner.green(),corner.blue()),235)
        window.close()

    def test_music_link_runs_in_background_and_selects_the_song(self):
        with tempfile.TemporaryDirectory() as d:
            window=Studio(QSettings(str(Path(d)/'link.ini'),QSettings.IniFormat))
            window.music_folder=d
            song=str(Path(d)/'Artist - Song [id].opus')
            with patch('montage_editor.desktop.RenderJob') as job, \
                 patch('montage_editor.music_sources.add_music',return_value=dict(path=song,source='youtube')) as add, \
                 patch('montage_editor.desktop.QMessageBox.information') as info:
                window.add_music_link('https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M')
                info.assert_called_once(); job.assert_not_called()
                window.add_music_link('https://youtu.be/abc')
                self.assertFalse(window.link_button.isEnabled())
                result=job.call_args.args[0]()
                add.assert_called_once_with('https://youtu.be/abc',d)
                window.music_link_added(result)
            self.assertEqual(window.music_path,str(Path(song).resolve()))
            self.assertIn('Added from YouTube',window.status.text())
            window.job=None;window.close()

    def test_tempo_override_and_tap_tempo(self):
        window=Studio()
        self.assertNotIn('beat_override',window.story())
        with patch('time.monotonic',side_effect=[10.0,10.5,11.0,11.5,12.0]):
            for _ in range(5): window.tap_tempo()
        self.assertAlmostEqual(window.tempo_override.value(),120.0)
        window.first_downbeat.setValue(1.25)
        self.assertEqual(window.story()['beat_override'],dict(bpm=120.0,first_downbeat=1.25))
        with patch('time.monotonic',side_effect=[0.0,0.25,0.5,0.75]):
            for _ in range(4): window.tap_tempo()   # 240 BPM taps fold into range
        self.assertAlmostEqual(window.tempo_override.value(),120.0)
        window.tempo_override.setValue(0)
        self.assertNotIn('beat_override',window.story())
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

    def test_quick_create_connects_quality_and_cinematic_engine(self):
        window=Studio()
        window.director_mode.setCurrentIndex(0)
        window.footage.addItem('clip.mp4');window.music_path='song.wav'
        with patch.object(window,'resolve_song',return_value=True), \
             patch('montage_editor.desktop.RenderJob') as job, \
             patch('montage_editor.desktop.create_montage') as create:
            window.export(automatic=True)
            operation=job.call_args.args[0]
            operation()
            settings,story=create.call_args.args[3:5]
            self.assertEqual((settings.width,settings.height),(1920,1080))
            self.assertEqual(settings.quality,'high')
            self.assertEqual(story['transition'],'cinematic')
            self.assertEqual(story['faith_message'],'Keep the faith.')
            self.assertEqual(window.create_button.text(),'Creating your montage…')
            self.assertTrue(story['auto_music_section'])
            self.assertTrue(story['normalize_audio'])
        window.job=None
        window.close()

    def test_claude_editor_mode_is_explicit_and_reaches_generator(self):
        from montage_editor.vision_director import ClaudeDirector
        window=Studio()
        window.director_mode.setCurrentIndex(0)
        self.assertTrue(window.director_note.isHidden())
        window.director_mode.setCurrentIndex(2)
        self.assertFalse(window.director_note.isHidden())
        self.assertIn('sent to Anthropic',window.director_note.text())
        self.assertFalse(window.ai_model.isEnabled())
        window.footage.addItem('clip.mp4');window.music_path='song.wav'
        with patch.object(window,'resolve_song',return_value=True), \
             patch('montage_editor.desktop.RenderJob') as job, \
             patch('montage_editor.desktop.create_montage') as create:
            window.export(automatic=True)
            job.call_args.args[0]()
            self.assertIsInstance(create.call_args.kwargs['ai_editor'],ClaudeDirector)
            self.assertIsNone(create.call_args.args[5])
        window.job=None
        window.director_mode.setCurrentIndex(0)
        window.close()

    def test_story_tone_is_subtle_by_default_and_custom_line_survives_reload(self):
        with tempfile.TemporaryDirectory() as d:
            prefs=QSettings(str(Path(d)/'tone.ini'),QSettings.IniFormat)
            window=Studio(prefs)
            self.assertEqual(window.story_tone.currentData(),'subtle')
            self.assertEqual(window.story()['faith_message'],'Keep the faith.')
            self.assertFalse(window.play_button.isEnabled())
            window.story_tone.setCurrentIndex(window.story_tone.findData('christian'))
            self.assertEqual(window.story()['faith_message'],'Walk with Christ.')
            window.closing_line.setText('Hope carries us.');window.save_preferences();window.close()
            restored=Studio(prefs)
            self.assertEqual(restored.story_tone.currentData(),'christian')
            self.assertEqual(restored.story()['faith_message'],'Hope carries us.')
            restored.story_tone.setCurrentIndex(restored.story_tone.findData('neutral'))
            self.assertEqual(restored.story()['faith_message'],'Hope carries us.')
            restored.closing_line.setText('')
            self.assertEqual(restored.story()['faith_message'],'')
            restored.close()

    def test_background_job_reports_failures(self):
        errors=[]
        def fail(): raise ValueError('invalid media')
        job=RenderJob(fail)
        job.failed.connect(errors.append)
        job.start(); self.assertTrue(job.wait(5000)); self.app.processEvents()
        self.assertEqual(errors,['invalid media'])
