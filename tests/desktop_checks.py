"""Run explicitly in the desktop CI job with QT_QPA_PLATFORM=offscreen."""
import unittest
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

    def test_background_job_reports_failures(self):
        errors=[]
        def fail(): raise ValueError('invalid media')
        job=RenderJob(fail)
        job.failed.connect(errors.append)
        job.start(); self.assertTrue(job.wait(5000)); self.app.processEvents()
        self.assertEqual(errors,['invalid media'])
