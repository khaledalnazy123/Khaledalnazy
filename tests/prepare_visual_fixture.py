from pathlib import Path
import os,sys,subprocess,shutil,io,math
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mv_core import Catalog
base=Path('/mnt/data/MovieVault_visual_qa');shutil.rmtree(base,ignore_errors=True);base.mkdir()
movies=base/'Films';movies.mkdir();c=Catalog(base/'appdata');c.set_settings({'auto_posters':'0'})
master=base/'sample.mkv'
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=black:s=640x360:r=24','-f','lavfi','-i','sine=frequency=440','-t','1','-c:v','mpeg4','-c:a','aac','-shortest',str(master)],check=True)
titles=[('The Last Horizon',2024,'4K','BluRay','QxR'),('Shadow Protocol',2023,'1080p','BluRay','YTS'),('Crimson Tide',2024,'1080p','WEB-DL','FLUX'),('The Silent Forest',2022,'720p','WEBRip','PSA'),('Neon Skies',2023,'4K','BluRay','RARBG'),('The Broken Circle',2021,'1080p','BluRay','YTS'),('Echoes of Tomorrow',2024,'4K','Remux','QxR'),('Velvet Nights',2022,'1080p','WEB-DL','NTB'),('The Empty City',2020,'1080p','BluRay','YTS'),('Solaris Falls',2023,'4K','BluRay','QxR'),('The Painter',2021,'1080p','WEB-DL','EVO'),('Beneath The Surface',2019,'720p','WEBRip','YTS')]
palettes=[('#0d3956','#d6b876'),('#38352d','#9c5b3c'),('#5e1219','#e5a54b'),('#0e3735','#a1c29a'),('#272064','#e04f89'),('#292d39','#e8dfcd'),('#174456','#de9445'),('#5b1524','#a94752'),('#4a535e','#d6d0c9'),('#133a67','#ce8352'),('#163145','#f8c4a0'),('#202838','#91abbc')]
fontfile='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf';font=ImageFont.truetype(fontfile,33);small=ImageFont.truetype(fontfile,17)
for i,(title,yr,res,src,grp) in enumerate(titles):
 folder=movies/title;folder.mkdir();fp=folder/f'{title} ({yr}) [{res}] [{src}] [{grp}].mkv';shutil.copyfile(master,fp)
 if i in (0,3,4):(folder/f'{title}.en.srt').write_text('1\n00:00:00,000 --> 00:00:00,500\nHello there!\n',encoding='utf-8')
 # Original demo posters made of geometry only, no scraped artwork
 a,b=palettes[i];im=Image.new('RGB',(460,690),a);d=ImageDraw.Draw(im)
 for y in range(690):
  alpha=y/690
  # intentionally visual variation
  col=tuple(int(int(a[j:j+2],16)*(1-alpha)+int(b[j:j+2],16)*alpha*.65) for j in (1,3,5))
  d.line([(0,y),(460,y)],fill=col)
 for j in range(18):
  angle=(j+i/10)*math.pi/9;x=230+int(160*math.sin(angle));y=240+int(138*math.cos(angle));d.ellipse((x-7,y-7,x+7,y+7),fill='#d5dbe2')
 d.ellipse((70,100,390,420),outline='#e7dac3',width=3)
 d.polygon([(0,570),(120,410),(270,545),(390,460),(460,560),(460,690),(0,690)],fill='#0a1725')
 from textwrap import wrap
 lines=title.upper().split(' ');current='';rows=[]
 for word in lines:
  if len((current+' '+word).strip())>13:
   rows.append(current);current=word
  else:current=(current+' '+word).strip()
 if current:rows.append(current)
 for j,line in enumerate(rows):
  box=d.textbbox((0,0),line,font=font);x=(460-(box[2]-box[0]))/2;d.text((x,500+j*39),line,font=font,fill='#f9f8eb')
 d.text((196,647),str(yr),font=small,fill='#ced7e5')
 im.save(folder/'poster.jpg',quality=88)
root=c.add_root(movies);job=c.scan([root['id']]);import time
while c.job(job)['state']=='running':time.sleep(.05)
print('Scan result:',c.job(job));ids={m['display_title']:m['id'] for m in c.movies(limit=100)['items']}
# turn two films into Missing to demonstrate archive without removing stored posters
for name in ('The Empty City','Beneath The Surface'):
 folder=movies/name;next(folder.glob('*.mkv')).unlink()
job=c.scan([root['id']])
while c.job(job)['state']=='running':time.sleep(.05)
print('Second scan:',c.job(job));print('Fixture data:',base)
