import shutil,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_playback import playback_plan,launch_playback,PlaybackError,SubtitleChoiceRequired
class PlaybackTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  d=Path(self.tmp.name);self.video=d/'My Movie.mkv';self.video.write_bytes(b'video')
  self.ar=d/'arabic.osn.srt';self.ar.write_text('Arabic')
  self.en=d/'english.netflix.srt';self.en.write_text('English')
  self.movie={'path':str(self.video),'status':'available','playback_preference':'auto','preferred_subtitle_id':None,
              'subtitles':[{'id':1,'kind':'external','filename':self.ar.name,'language':'Arabic','source':'OSN'},
                           {'id':2,'kind':'external','filename':self.en.name,'language':'English','source':'Netflix'}]}
 def test_multiple_subtitles_ask_without_renaming(self):
  with self.assertRaises(SubtitleChoiceRequired):playback_plan(self.movie)
  plan=playback_plan(self.movie,subtitle_id=2)
  self.assertEqual(plan['subtitle'],str(self.en))
  self.assertEqual(sorted(x.name for x in self.video.parent.iterdir()),sorted([self.video.name,self.ar.name,self.en.name]))
 def test_selected_preference_is_reversible(self):
  self.movie['playback_preference']='selected';self.movie['preferred_subtitle_id']=1
  self.assertEqual(playback_plan(self.movie)['subtitle'],str(self.ar))
  self.movie['playback_preference']='ask'
  with self.assertRaises(SubtitleChoiceRequired):playback_plan(self.movie)
  self.assertTrue(playback_plan(self.movie,no_subtitles=True)['mute_subtitles'])
 def test_reject_non_member_id_missing_and_symlink(self):
  with self.assertRaises(PlaybackError):playback_plan(self.movie,subtitle_id=100)
  self.ar.unlink()
  with self.assertRaises(PlaybackError):playback_plan(self.movie,subtitle_id=1)
  self.ar.symlink_to(self.en)
  with self.assertRaises(PlaybackError):playback_plan(self.movie,subtitle_id=1)
 def test_mpv_command_is_argument_list_and_original_unmodified(self):
  before=self.ar.read_bytes();plan=playback_plan(self.movie,subtitle_id=1)
  with patch('mv_playback.find_player',return_value=('mpv','/fake/mpv')), patch('mv_playback.subprocess.Popen') as run:
   result=launch_playback(plan)
   args=run.call_args.args[0]
   self.assertEqual(args[-1],str(self.video))
   self.assertIn('--sub-file='+str(self.ar),args)
   self.assertTrue(result['subtitle_loaded'])
  self.assertEqual(self.ar.read_bytes(),before)

if __name__=='__main__':unittest.main()
