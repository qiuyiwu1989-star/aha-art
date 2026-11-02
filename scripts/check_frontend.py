from pathlib import Path
from html.parser import HTMLParser
import subprocess,tempfile
class Scripts(HTMLParser):
 def __init__(self):super().__init__();self.active=False;self.parts=[]
 def handle_starttag(self,tag,attrs):
  if tag=='script':
   a=dict(attrs);self.active='src' not in a and a.get('type') not in ('importmap','application/json','application/ld+json')
   if self.active:self.parts.append('')
 def handle_endtag(self,tag):
  if tag=='script':self.active=False
 def handle_data(self,data):
  if self.active:self.parts[-1]+=data
changed=subprocess.check_output(['git','diff','--name-only','HEAD'],text=True).splitlines()
new=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines()
pages=set('web/'+p+'.html' for p in ['museum','art','dashboard','kg-catalog','kg-galaxy','kg-style-3d'])
pages.update(p for p in changed+new if p.startswith('web/') and p.endswith('.html'))
for page in sorted(pages):
 parser=Scripts();parser.feed(Path(page).read_text())
 for script in parser.parts:
  with tempfile.NamedTemporaryFile(suffix='.mjs',mode='w') as f:
   f.write(script);f.flush();r=subprocess.run(['node','--check',f.name],capture_output=True,text=True)
   if r.returncode:raise SystemExit(page+': '+r.stderr)
scripts=set(['web/js/aha-images.js','web/js/aha-request.js','web/js/imgguard.js','web/js/frames.js','web/aha-mem.js','web/sw.js'])
scripts.update(p for p in changed+new if p.startswith('web/') and p.endswith('.js'))
for f in sorted(scripts):subprocess.run(['node','--check',f],check=True)
for page in ['museum','art']:assert 'exhibit?limit=8000' not in Path('web',page+'.html').read_text()
print(f'{len(pages)} pages and {len(scripts)} scripts syntax passed; museum/art no 8000 request')
