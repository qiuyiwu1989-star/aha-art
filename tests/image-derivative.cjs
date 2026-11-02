const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('oversized asset uses verified local variants for local and COS sources',()=>{
 const window={location:{href:'http://127.0.0.1:8766/',origin:'http://127.0.0.1:8766'}};vm.runInNewContext(fs.readFileSync('web/js/aha-images.js','utf8'),{window,URL});
 const path='/artworks/'+encodeURIComponent('油画数据集')+'/yh/upload/workImage_ori/20160901/20160901112148rxyIzJmh.jpg';
 for(const src of ['/img'+path,'https://aha-1254041526.cos.ap-shanghai.myqcloud.com'+path+'?imageMogr2/thumbnail/600x600']){
  assert.equal(window.AHAImages.url(src,{size:640}),'http://127.0.0.1:8766/assets/derivatives/34754-720.webp');
  assert.equal(window.AHAImages.url(src,{size:1600}),'http://127.0.0.1:8766/assets/derivatives/34754-1600.webp');
 }
});
