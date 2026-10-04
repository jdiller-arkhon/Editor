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

    def test_cancel_reports_without_an_error_dialog(self):
        from montage_editor import jobs
        window=Studio()
        job=RenderJob(lambda:(_ for _ in ()).throw(jobs.Cancelled('Cancelled')))
        messages=[]
        job.failed.connect(messages.append)
        job.run()
        self.assertEqual(messages,['Cancelled'])
        with patch('montage_editor.desktop.QMessageBox.warning') as warning:
            window.failed(messages[0])
            warning.assert_not_called()
        self.assertIn('nothing was saved',window.status.text())
        window.on_progress(.42,'Rendering shot 3 of 9')
        self.assertEqual(window.progress.value(),420)
        self.assertIn('42%',window.status.text())
        window.close()

    def test_presets_preview_finalise_and_shot_editing(self):
        import subprocess,json
        with tempfile.TemporaryDirectory() as d:
            window=Studio(QSettings(str(Path(d)/'flow.ini'),QSettings.IniFormat))
            window.director_mode.setCurrentIndex(window.director_mode.findData('activity'))
            window.export_preset.setCurrentIndex(window.export_preset.findData('shorts-1080x1920'))
            self.assertEqual((window.delivery_settings().width,window.delivery_settings().height),(1080,1920))
            window.footage.addItem('clip.mp4');window.music_path='song.wav'
            with patch.object(window,'resolve_song',return_value=True), \
                 patch('montage_editor.desktop.RenderJob') as job, \
                 patch('montage_editor.desktop.create_montage') as create:
                window.export(automatic=True,preview=True)
                job.call_args.args[0]()
                settings,story=create.call_args.args[3:5]
                self.assertEqual((settings.width,settings.height,settings.quality),(360,640,'draft'))
                self.assertEqual(story['interpolation'],'blend')
            window.job=None
            video=Path(d)/'v.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-t','30',
                            '-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True)
            draft=Timeline(1,'song.wav',draft_settings:=dict(Settings(width=360,height=640,quality='draft').__dict__),
                           [Clip(str(video),2,2,.5),Clip(str(video),10,3,.7)])
            preview=Path(d)/'p.timeline.json';draft.save(preview)
            (Path(d)/'p.analysis.json').write_text(json.dumps({'candidates':[
                dict(source=str(video),time=25.0,score=.9,source_duration=30.0,event='clutch')]}))
            window.completed(dict(duration=5,width=360,height=640),str(Path(d)/'p.mp4'),False,True)
            self.assertTrue(window.finalize_button.isEnabled())
            with patch('montage_editor.desktop.RenderJob') as job, patch('montage_editor.desktop.render') as render:
                window.finalize_preview()
                job.call_args.args[0]()
                final=render.call_args.args[0]
            self.assertEqual((final.settings['width'],final.settings['height'],final.settings['quality']),(1080,1920,'high'))
            self.assertEqual(final.interpolation,'motion')
            window.job=None
            window.show_timeline(draft);window.timeline_table.selectRow(0)
            self.assertTrue(all(b.isEnabled() for b in window.edit_buttons))
            window.move_selected(1)
            self.assertTrue(window.timeline.clips[1].start<=3<=window.timeline.clips[1].start+3)
            window.timeline_table.selectRow(0)
            with patch('montage_editor.desktop.QInputDialog.getItem',return_value=(None,True)) as item:
                item.side_effect=lambda *a,**k:(a[3][0],True)
                window.swap_selected()
            self.assertTrue(window.timeline.clips[0].start<=25<=window.timeline.clips[0].start+2)
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
            # The side panel opens on the director chat; the manual form is collapsed until asked for.
            self.assertFalse(restored.inspector_scroll.isHidden())
            self.assertTrue(restored.manual_controls.isHidden())
            restored.toggle_advanced()
            self.assertFalse(restored.manual_controls.isHidden())
            self.assertEqual(restored.manual_toggle.text(),'Manual controls ▾')
            restored.toggle_advanced()
            self.assertTrue(restored.manual_controls.isHidden())
            restored.show_advanced(restored.look)                       # Effects/AI Director nav opens the form
            self.assertFalse(restored.manual_controls.isHidden())
            restored.close()

    def test_quick_create_connects_quality_and_cinematic_engine(self):
        window=Studio()
        window.director_mode.setCurrentIndex(window.director_mode.findData('activity'))
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
            self.assertEqual((story['look'],story['interpolation'],story['motion_blur'],story['sfx'],story['reframe']),
                             ('clean','motion',True,'swish','auto'))
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
        window.director_mode.setCurrentIndex(window.director_mode.findData('activity'))
        window.close()

    def test_local_ai_director_is_the_default_and_must_be_ready(self):
        from montage_editor.vision_director import LocalDirector
        with tempfile.TemporaryDirectory() as d:
            prefs=QSettings(str(Path(d)/'local.ini'),QSettings.IniFormat)
            window=Studio(prefs)
            self.assertEqual(window.director_mode.currentData(),'local')
            self.assertEqual(window.ai_model.text(),'qwen3.5:9b')
            self.assertTrue(window.ai_model.isEnabled() and window.setup_button.isEnabled())
            window.footage.addItem('clip.mp4');window.music_path='song.wav'
            with patch.object(window,'resolve_song',return_value=True), \
                 patch('montage_editor.local_ai.readiness',return_value=(False,'Ollama is not running on this computer.')), \
                 patch('montage_editor.desktop.QMessageBox.warning') as warning, \
                 patch('montage_editor.desktop.RenderJob') as job:
                window.export(automatic=True)
                job.assert_not_called()
                self.assertIn('Ollama is not running',warning.call_args.args[2])
                self.assertIn('activity engine',warning.call_args.args[2])
            with patch.object(window,'resolve_song',return_value=True), \
                 patch('montage_editor.local_ai.readiness',return_value=(True,'qwen3.5:9b is ready')), \
                 patch('montage_editor.desktop.RenderJob') as job, \
                 patch('montage_editor.desktop.create_montage') as create:
                window.export(automatic=True)
                job.call_args.args[0]()
                editor=create.call_args.kwargs['ai_editor']
                self.assertIsInstance(editor,LocalDirector)
                self.assertEqual((editor.model,editor.director_model),('qwen3.5:9b','qwen3.5:9b'))
                self.assertEqual(window.local_status.text(),'qwen3.5:9b is ready')
            window.job=None;window.close()
            old=QSettings(str(Path(d)/'old.ini'),QSettings.IniFormat)
            old.setValue('director_mode',2);old.setValue('local_model','qwen2.5vl:7b')
            migrated=Studio(old)
            self.assertEqual(migrated.director_mode.currentData(),'claude')
            self.assertEqual(migrated.ai_model.text(),'qwen3.5:9b')        # the old default moves to the better model
            migrated.close()
            old.setValue('local_model','llava:13b')
            custom=Studio(old)
            self.assertEqual(custom.ai_model.text(),'llava:13b')           # a deliberate choice is kept
            custom.close()

    def test_director_chat_changes_the_edit_through_the_controls(self):
        from types import SimpleNamespace
        from montage_editor.vision_director import LocalDirector
        answer=dict(reply='Faster pace, a punchy look and 45 s; making a preview.',
                    actions=[dict(action='set_pace',value='fast'),dict(action='set_length',value='45'),
                             dict(action='set_look',value='punchy'),dict(action='make',value='preview'),
                             dict(action='format_disk',value='C:')])
        with tempfile.TemporaryDirectory() as d:
            window=Studio(QSettings(str(Path(d)/'chat.ini'),QSettings.IniFormat))
            self.assertEqual(window.chat_chip.text(),'On this computer')
            window.closing_line.setText('Hope carries us.')
            with patch('montage_editor.local_ai.readiness',return_value=(True,'ready')), \
                 patch.object(LocalDirector,'_call',return_value=(answer,SimpleNamespace(model='qwen3.5:9b'))) as call, \
                 patch.object(window,'export') as export:
                window.chat_input.setText('Make it more intense, 45 seconds with a punchy colour look, then show me')
                window.send_chat()
                window.chat_job.wait(10000);self.app.processEvents();self.app.processEvents()
                prompt=call.call_args.args[0]['text']
                self.assertIn('Make it more intense, 45 seconds',prompt)
                self.assertIn('"pace": "balanced"',prompt)
                export.assert_called_once_with(automatic=True,preview=True)
            self.assertEqual((window.pace.currentData(),window.duration.value(),window.look.currentData()),('fast',45,'punchy'))
            self.assertEqual(window.closing_line.text(),'Hope carries us.')      # not asked, not changed
            log=window.chat_log.toPlainText()
            self.assertIn('Faster pace',log);self.assertIn('Pace → Fast',log)
            self.assertIn('format_disk',log);self.assertIn('unknown action',log)
            self.assertIsNone(window.chat_job);self.assertTrue(window.chat_send.isEnabled())
            # Ollama unavailable: explained in the chat, nothing changes.
            with patch('montage_editor.local_ai.readiness',return_value=(False,'Ollama is not running on this computer.')):
                window.chat_input.setText('Slower please');window.send_chat()
                window.chat_job.wait(10000);self.app.processEvents();self.app.processEvents()
            self.assertIn('Ollama is not running',window.chat_log.toPlainText())
            self.assertEqual(window.pace.currentData(),'fast')
            window.close()

    def test_chat_styles_and_shot_edits_drive_the_app(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            window=Studio(QSettings(str(Path(d)/'talents.ini'),QSettings.IniFormat))
            window.apply_chat_actions([('apply_style','chill')])
            self.assertEqual((window.pace.currentData(),window.look.currentData(),window.sfx.isChecked(),window.beat_fx.isChecked()),
                             ('calm','clean',False,False))
            window.apply_chat_actions([('apply_style','hype')])
            self.assertEqual((window.pace.currentData(),window.look.currentData(),window.beat_fx.isChecked()),('fast','punchy',True))
            self.assertIn('Style → hype',window.chat_log.toPlainText())
            video=Path(d)/'v.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=30','-t','20',
                            '-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True)
            window.show_timeline(Timeline(1,'song.wav',Settings().__dict__,
                                          [Clip(str(video),1,2,.5),Clip(str(video),6,2,.9),Clip(str(video),11,2,.4)],
                                          transition='cinematic',boundary_transitions=['cut','cut']))
            window.music_facts=dict(beats=[2.5,3.0,3.5],phrases=[dict(time=2.0,kinds=['drop'])])
            window.apply_chat_actions([('set_shot','2 slow motion'),('set_cut','1 dissolve')])
            self.assertEqual(window.timeline.clips[1].speed_profile,'ramp')
            self.assertEqual(window.timeline.boundary_transitions,['fade','cut'])
            facts=window.chat_state()['shots']
            self.assertEqual((facts[1]['treatment'],facts[1]['music'],facts[0]['transition_out']),('slow motion',['drop'],'dissolve'))
            window.apply_chat_actions([('set_shot','3 slow motion'),('set_cut','3 dissolve')])
            log=window.chat_log.toPlainText()
            self.assertIn('last shot has no transition',log)          # explained, nothing changed
            with patch.object(window,'export') as export,patch.object(window,'export_formats') as formats:
                window.apply_chat_actions([('make','render')]);window.apply_chat_actions([('make','formats')])
                export.assert_called_once_with(replay=True);formats.assert_called_once()
            window.close()

    def test_loading_a_montage_never_cuts_off_the_timeline_or_chat(self):
        # Real order: the window is open, then a finished montage loads. The page once stopped
        # growing at 720 px here, hiding the timeline and the director chat.
        with tempfile.TemporaryDirectory() as d:
            window=Studio(QSettings(str(Path(d)/'page.ini'),QSettings.IniFormat))
            window.resize(1520,1000);window.show();self.app.processEvents()
            window.show_timeline(Timeline(1,'song.wav',Settings().__dict__,[Clip('v.mp4',1,2,.5),Clip('v.mp4',5,2,.5)]))
            self.app.processEvents()
            page=window.body_scroll.widget()
            for panel in (window.lanes,window.timeline_table):
                self.assertTrue(panel.isVisible())
                self.assertLessEqual(panel.mapTo(page,panel.rect().bottomLeft()).y(),page.height())
            # The chat lives in the side panel and fits it: nothing wider than the window.
            self.assertTrue(window.chat_panel.isVisible())
            self.assertLessEqual(page.width(),window.body_scroll.viewport().width())
            side=window.inspector_scroll
            self.assertLessEqual(window.chat_panel.mapTo(side.widget(),window.chat_panel.rect().topRight()).x(),
                                 side.viewport().width())
            window.resize(1200,820);self.app.processEvents()               # also at the minimum window size
            self.assertLessEqual(page.width(),window.body_scroll.viewport().width())
            self.assertLessEqual(side.widget().width(),side.viewport().width())
            window.close()

    def test_any_song_can_be_pasted_into_one_box(self):
        with tempfile.TemporaryDirectory() as d:
            window=Studio(QSettings(str(Path(d)/'song.ini'),QSettings.IniFormat))
            song=Path(d)/'Some Artist - Anthem.flac';song.touch()
            window.song_name.setText(f'"{song}"')
            self.assertTrue(window.resolve_song())
            self.assertEqual(window.music_path,str(song.resolve()))
            library=Path(d)/'library'
            downloaded=library/'Linked Song.m4a'
            def fake_add(link,folder,**options):
                Path(folder).mkdir(parents=True,exist_ok=True);downloaded.touch()
                return dict(path=str(downloaded),source='youtube',folder=folder,link=link)
            after=[]
            window.clear_music_selection();window.song_name.setText('https://youtu.be/abc123')
            with patch.object(window,'music_library',return_value=library), \
                 patch('montage_editor.music_sources.add_music',side_effect=fake_add) as add:
                self.assertFalse(window.resolve_song(then=lambda:after.append(window.music_path)))
                window.job.wait(10000)
                for _ in range(5):self.app.processEvents()
            self.assertEqual(add.call_args.args[:2],('https://youtu.be/abc123',str(library)))   # no folder prompt
            self.assertEqual(after,[str(downloaded.resolve())])                                # then carried on
            window.close()

    def test_every_format_export_uses_the_loaded_edit(self):
        with tempfile.TemporaryDirectory() as d:
            window=Studio(QSettings(str(Path(d)/'fmt.ini'),QSettings.IniFormat))
            self.assertFalse(window.formats_button.isEnabled())
            timeline=Timeline(1,'song.wav',Settings().__dict__,[Clip('v.mp4',0,2,.5)])
            window.show_timeline(timeline)
            self.assertTrue(window.formats_button.isEnabled())
            with patch('montage_editor.desktop.RenderJob') as job, patch('montage_editor.pipeline.render_formats') as formats:
                window.export_formats()
                job.call_args.args[0]()
                self.assertIs(formats.call_args.args[0],timeline)
            window.formats_done([dict(format='youtube-1080p30',path=str(Path(d)/'a.mp4'),width=1920,height=1080,duration=2,full_decode=True),
                                 dict(format='shorts-1080x1920',path=str(Path(d)/'b.mp4'),width=1080,height=1920,duration=2,full_decode=True)])
            self.assertIn('shorts-1080x1920 1080×1920',window.status.text())
            window.job=None;window.close()

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
