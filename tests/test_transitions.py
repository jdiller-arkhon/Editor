import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from montage_editor.config import Settings
from montage_editor.pipeline import Clip, Timeline, render, create_montage


class CompositeTests(unittest.TestCase):
    def test_two_real_images_blend_without_moving_cut_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('red','blue'):
                subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                    f'color=c={name}:s=160x90:r=24','-t','2','-c:v','libx264','-threads','2',
                    str(root/f'{name}.mp4')],check=True)
            music=root/'music.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=220',
                            '-t','4',str(music)],check=True)
            for style in ('push','dissolve','zoom_blend','blur','cinematic'):
                timeline=Timeline(1,str(music),Settings(width=160,height=90,fps=24).__dict__,
                    [Clip(str(root/'red.mp4'),0,2,1),Clip(str(root/'blue.mp4'),0,2,1)],
                    transition=style,transition_duration=.5)
                output=root/f'{style}.mp4'
                report=render(timeline,output)
                self.assertTrue(report['full_decode'])
                self.assertAlmostEqual(report['duration'],4,delta=.08)
                boundary=report['transition_boundaries'][0]
                self.assertEqual(boundary['at'],2)
                self.assertEqual(boundary['start'],1.75)
                self.assertEqual(report['render_quality']['crf'],16)
                if style in ('push','dissolve','cinematic'):
                    raw=subprocess.run(['ffmpeg','-v','error','-ss','2','-i',str(output),
                        '-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1'],
                        capture_output=True,check=True).stdout
                    pixels=np.frombuffer(raw,dtype=np.uint8).reshape(-1,3)
                    self.assertGreater(pixels[:,0].mean(),40)
                    self.assertGreater(pixels[:,2].mean(),40)

    def test_auto_music_excerpt_is_analyzed_and_rendered_from_same_offset(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);video=root/'video.mp4';music=root/'song.wav'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',
                'testsrc2=size=160x90:rate=24','-t','8','-c:v','libx264','-threads','2',str(video)],check=True)
            expression='aevalsrc=sin(2*PI*if(lt(t\\,4)\\,220\\,880)*t)*if(lt(t\\,4)\\,0.02\\,0.5):s=8000'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',expression,'-t','8',str(music)],check=True)
            output=root/'excerpt.mp4'
            settings=Settings(width=160,height=90,fps=24,duration=4,minimum_clip=2,maximum_clip=2)
            report=create_montage([video],music,output,settings,
                story=dict(auto_music_section=True,edit_profile='cinematic',transition='cinematic'))
            self.assertGreaterEqual(report['music_start'],3.5)
            timeline=Timeline.load(output.with_suffix('.timeline.json'))
            self.assertEqual(timeline.music_start,report['music_start'])
            raw=subprocess.run(['ffmpeg','-v','error','-i',str(output),'-vn','-ac','1','-ar','8000',
                '-f','f32le','pipe:1'],capture_output=True,check=True).stdout
            samples=np.frombuffer(raw,dtype='<f4')[8000:16000]
            spectrum=abs(np.fft.rfft(samples))
            self.assertGreater(spectrum[880],spectrum[220]*10)

    def test_quality_validation(self):
        with self.assertRaises(ValueError):
            Settings(quality='made-up')
